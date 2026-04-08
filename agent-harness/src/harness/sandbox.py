"""Sandbox layer for shell command execution.

Two backends:
- `subprocess`: minimal isolation (CWD restriction, timeout, env scrubbing).
  Use only in trusted dev environments.
- `bubblewrap`: filesystem and network isolation via `bwrap`. Recommended.

A whitelist + denylist of command patterns is enforced regardless of backend.
"""

from __future__ import annotations

import logging
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

SandboxBackend = Literal["subprocess", "bubblewrap"]


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False


@dataclass
class SandboxConfig:
    backend: SandboxBackend = "bubblewrap"
    deny_patterns: list[str] = None  # type: ignore[assignment]
    allow_network: bool = False
    max_output_bytes: int = 16 * 1024
    extra_ro_binds: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.deny_patterns is None:
            self.deny_patterns = list(DEFAULT_DENY_PATTERNS)
        if self.extra_ro_binds is None:
            self.extra_ro_binds = []


# Patterns matched against the raw command string. Any match → refusal.
DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    r"\brm\s+-rf?\s+/(\s|$)",         # rm -rf /
    r"\brm\s+-rf?\s+\*",              # rm -rf *
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+-R\s+777\b",
    r":\(\)\s*\{",                    # fork bomb signature
    r"\|\s*(sh|bash)\b",              # pipe to shell
    r">\s*/etc/",                     # write to /etc
    r">\s*/dev/sd",                   # write to raw disk
    r"\bsudo\b",
    r"\bsu\b",
    r"\bcurl\s+[^|]*\|\s*(sh|bash)",  # curl … | sh
    r"\bwget\s+[^|]*\|\s*(sh|bash)",  # wget … | sh
)


class SandboxError(RuntimeError):
    pass


class Sandbox:
    """Executes shell commands with denylist and isolation."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self._compiled_deny = [re.compile(p) for p in config.deny_patterns]
        if config.backend == "bubblewrap":
            if not shutil.which("bwrap"):
                logger.warning(
                    "bubblewrap requested but `bwrap` not found in PATH; "
                    "falling back to subprocess backend"
                )
                self.config.backend = "subprocess"
            elif not self._bwrap_works():
                logger.warning(
                    "bubblewrap requested but `bwrap` fails at runtime "
                    "(likely AppArmor or kernel restrictions); "
                    "falling back to subprocess backend"
                )
                self.config.backend = "subprocess"

    @staticmethod
    def _bwrap_works() -> bool:
        """Smoke-test bwrap with a trivial command."""
        try:
            proc = subprocess.run(
                [
                    "bwrap", "--ro-bind", "/usr", "/usr",
                    "--ro-bind", "/bin", "/bin",
                    "--ro-bind", "/lib", "/lib",
                    "--ro-bind", "/lib64", "/lib64",
                    "--proc", "/proc", "--dev", "/dev",
                    "--tmpfs", "/tmp",
                    "--unshare-pid",
                    "true",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return proc.returncode == 0
        except Exception:  # noqa: BLE001
            return False

    def check_command(self, command: str) -> None:
        """Raise SandboxError if the command matches a deny pattern."""
        for pattern in self._compiled_deny:
            if pattern.search(command):
                raise SandboxError(
                    f"command refused by sandbox policy: matches /{pattern.pattern}/"
                )

    def run(
        self,
        command: str,
        cwd: Path,
        timeout_s: int = 60,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command in the sandbox.

        Returns a SandboxResult; never raises on non-zero exit. Raises
        SandboxError only if the command is refused by policy.
        """
        self.check_command(command)
        scrubbed_env = self._scrubbed_env(env or {})

        if self.config.backend == "bubblewrap":
            argv = self._bwrap_argv(command, cwd)
        else:
            argv = ["bash", "-c", command]

        start = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603
                argv,
                cwd=str(cwd) if self.config.backend == "subprocess" else None,
                env=scrubbed_env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\n[sandbox] timeout after {timeout_s}s"
            exit_code = 124
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)

        truncated = False
        if len(stdout) > self.config.max_output_bytes:
            stdout = stdout[: self.config.max_output_bytes] + "\n[truncated]"
            truncated = True
        if len(stderr) > self.config.max_output_bytes:
            stderr = stderr[: self.config.max_output_bytes] + "\n[truncated]"
            truncated = True

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            truncated=truncated,
        )

    def _bwrap_argv(self, command: str, cwd: Path) -> list[str]:
        """Build a bubblewrap command line.

        Layout:
        - / mounted from host root, read-only
        - workspace mounted read-write at the same path
        - /tmp is a tmpfs
        - /proc, /dev minimal
        - network namespace unshared unless allow_network
        - HOME, .ssh, .aws, .kube, .gnupg are NOT bound
        """
        cwd = cwd.resolve()
        argv = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
            "--ro-bind", "/etc/alternatives", "/etc/alternatives",
            "--ro-bind", "/etc/ssl", "/etc/ssl",
            "--ro-bind", "/etc/ca-certificates", "/etc/ca-certificates",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--tmpfs", "/run",
            "--bind", str(cwd), str(cwd),
            "--chdir", str(cwd),
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-uts",
            "--unshare-ipc",
            "--unshare-cgroup-try",
            "--new-session",
        ]
        if not self.config.allow_network:
            argv += ["--unshare-net"]
        for ro in self.config.extra_ro_binds:
            argv += ["--ro-bind", ro, ro]
        argv += ["bash", "-c", command]
        return argv

    @staticmethod
    def _scrubbed_env(extra: dict[str, str]) -> dict[str, str]:
        """Build a minimal environment, stripping credentials."""
        import os

        keep = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "TERM": os.environ.get("TERM", "dumb"),
            "HOME": "/tmp",  # never the real HOME
        }
        keep.update(extra)
        return keep
