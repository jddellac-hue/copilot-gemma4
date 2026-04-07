"""Kubernetes tools (read-only by default).

Three tools wrapping `kubectl`:

- `kubectl_get`       — list resources of a type
- `kubectl_describe`  — detailed description of a single resource
- `kubectl_logs`      — logs of a pod (with optional container, tail, since)

Critical safety design — multi-environment guardrails
======================================================

The agent operates against ONE locked context and a known set of allowed
namespaces, both declared in the profile YAML. The model can choose a
namespace from the allowed list but cannot override the context. The
`--context` and (when locked) `--namespace` flags are injected by THIS
module, not by the model. There is no parameter that lets the model pass
arbitrary kubectl flags.

This design means:

- An agent in `prod-ro` cannot accidentally read `staging` (different
  context, refused at the harness level).
- An agent in `staging` cannot reach `prod` even if prompt-injected.
- Adding a new cluster requires editing the profile, not the code.

`kubectl` is invoked via subprocess.run with a hand-built argv. We do NOT
go through the bash sandbox tool because we want strict argv control:
the model never sees a shell line, only typed parameters that we map to
flags ourselves.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


# Resources the model is allowed to query. This is intentionally a
# whitelist — read-only kinds only. Adding mutating verbs requires editing
# this constant AND the tool's risk level.
ALLOWED_RESOURCES: frozenset[str] = frozenset(
    {
        "pods",
        "po",
        "deployments",
        "deploy",
        "statefulsets",
        "sts",
        "daemonsets",
        "ds",
        "services",
        "svc",
        "ingresses",
        "ing",
        "configmaps",
        "cm",
        "secrets",  # NOTE: only metadata is returned with -o, never decoded
        "nodes",
        "no",
        "namespaces",
        "ns",
        "persistentvolumeclaims",
        "pvc",
        "persistentvolumes",
        "pv",
        "events",
        "ev",
        "replicasets",
        "rs",
        "jobs",
        "cronjobs",
        "cj",
        "horizontalpodautoscalers",
        "hpa",
        "endpoints",
        "ep",
        "networkpolicies",
        "netpol",
    }
)


@dataclass
class KubernetesConfig:
    enabled: bool = False
    kubectl_path: str = "kubectl"
    context: str = ""
    allowed_namespaces: list[str] = field(default_factory=list)
    locked_namespace: str | None = None  # if set, model cannot pick another
    default_namespace: str = "default"
    timeout_s: int = 30
    max_log_lines: int = 500

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KubernetesConfig:
        return cls(
            enabled=data.get("enabled", False),
            kubectl_path=data.get("kubectl_path", "kubectl"),
            context=data.get("context", ""),
            allowed_namespaces=list(data.get("allowed_namespaces", [])),
            locked_namespace=data.get("locked_namespace"),
            default_namespace=data.get("default_namespace", "default"),
            timeout_s=int(data.get("timeout_s", 30)),
            max_log_lines=int(data.get("max_log_lines", 500)),
        )


def _resolve_namespace(
    config: KubernetesConfig, requested: str | None
) -> tuple[str | None, str | None]:
    """Resolve the namespace to use, returning (namespace, error_message).

    Order of precedence:
    1. If `locked_namespace` is set: it always wins. The model cannot
       override.
    2. Otherwise, if a namespace is requested: it must be in
       `allowed_namespaces`.
    3. Otherwise: fall back to `default_namespace`.
    """
    if config.locked_namespace:
        if requested and requested != config.locked_namespace:
            return (
                None,
                f"namespace is locked to {config.locked_namespace!r} for "
                f"this profile; requested {requested!r} refused",
            )
        return config.locked_namespace, None

    if requested:
        if requested not in config.allowed_namespaces:
            return (
                None,
                f"namespace {requested!r} not in allowed list "
                f"{config.allowed_namespaces}",
            )
        return requested, None

    return config.default_namespace, None


def _validate_resource_kind(kind: str) -> str | None:
    """Return an error message if `kind` is not in the allow-list."""
    if kind.lower() not in ALLOWED_RESOURCES:
        return (
            f"resource kind {kind!r} not in allow-list. "
            f"Allowed: {sorted(ALLOWED_RESOURCES)}"
        )
    return None


def _validate_name(name: str) -> str | None:
    """Refuse anything that doesn't look like a normal k8s name."""
    if not name:
        return "empty name"
    if len(name) > 253:
        return "name too long"
    # K8s DNS-1123 subdomain pattern (lowercase, dots, hyphens, digits)
    import re

    if not re.match(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$", name):
        return f"invalid k8s name: {name!r}"
    return None


def _build_argv(
    config: KubernetesConfig,
    verb: str,
    *args: str,
    namespace: str | None = None,
) -> list[str]:
    """Build a kubectl argv with locked context and validated namespace."""
    argv = [config.kubectl_path, verb, f"--context={config.context}"]
    if namespace:
        argv.append(f"--namespace={namespace}")
    argv += list(args)
    argv.append(f"--request-timeout={config.timeout_s}s")
    return argv


def _run(argv: list[str], timeout_s: int) -> tuple[int, str, str]:
    """Run kubectl, return (exit_code, stdout, stderr)."""
    logger.debug("kubectl exec: %s", argv)
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s + 5,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"kubectl timeout after {timeout_s}s"
    except FileNotFoundError as exc:
        return 127, "", f"kubectl not found: {exc}"


def build_kubernetes_tools(config: KubernetesConfig) -> list[Tool]:
    """Build the kubectl tools, or return [] if not enabled."""
    if not config.enabled:
        return []
    if not config.context:
        logger.warning("kubernetes enabled but `context` is empty; skipping")
        return []
    if not shutil.which(config.kubectl_path):
        logger.warning(
            "kubernetes enabled but `%s` not in PATH; tools will fail at runtime",
            config.kubectl_path,
        )

    ns_help = (
        f"locked to {config.locked_namespace!r}"
        if config.locked_namespace
        else f"one of {config.allowed_namespaces or [config.default_namespace]}"
    )

    @tool(
        name="kubectl_get",
        description=(
            f"List Kubernetes resources of a given kind. Context is locked "
            f"to {config.context!r}. Namespace is {ns_help}. The kind must "
            f"be one of: {', '.join(sorted(ALLOWED_RESOURCES))}. Output is "
            "tabular (the default kubectl format)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Resource kind, e.g. 'pods', 'deploy'",
                },
                "namespace": {
                    "type": "string",
                    "description": (
                        "Optional namespace. If omitted, the profile default "
                        "is used. Locked profiles ignore this field."
                    ),
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "Optional label selector, e.g. 'app=billing,tier=front'"
                    ),
                },
            },
            "required": ["kind"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def kubectl_get(args: dict) -> ToolResult:
        kind_err = _validate_resource_kind(args["kind"])
        if kind_err:
            return ToolResult(ok=False, content=kind_err)

        namespace, ns_err = _resolve_namespace(config, args.get("namespace"))
        if ns_err:
            return ToolResult(ok=False, content=ns_err)

        extra: list[str] = [args["kind"]]
        if args.get("selector"):
            extra += ["-l", args["selector"]]
        extra += ["-o", "wide"]

        argv = _build_argv(config, "get", *extra, namespace=namespace)
        rc, stdout, stderr = _run(argv, config.timeout_s)
        if rc != 0:
            return ToolResult(
                ok=False,
                content=f"kubectl get failed (exit {rc}): {stderr.strip()}",
            )
        return ToolResult(
            ok=True,
            content=stdout,
            metadata={
                "context": config.context,
                "namespace": namespace,
                "kind": args["kind"],
            },
        )

    @tool(
        name="kubectl_describe",
        description=(
            f"Describe a single Kubernetes resource (events, conditions, "
            f"history). Context is locked to {config.context!r}. Namespace "
            f"is {ns_help}."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "name": {"type": "string"},
                "namespace": {"type": "string"},
            },
            "required": ["kind", "name"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def kubectl_describe(args: dict) -> ToolResult:
        kind_err = _validate_resource_kind(args["kind"])
        if kind_err:
            return ToolResult(ok=False, content=kind_err)
        name_err = _validate_name(args["name"])
        if name_err:
            return ToolResult(ok=False, content=name_err)

        namespace, ns_err = _resolve_namespace(config, args.get("namespace"))
        if ns_err:
            return ToolResult(ok=False, content=ns_err)

        argv = _build_argv(
            config, "describe", args["kind"], args["name"], namespace=namespace
        )
        rc, stdout, stderr = _run(argv, config.timeout_s)
        if rc != 0:
            return ToolResult(
                ok=False,
                content=f"kubectl describe failed (exit {rc}): {stderr.strip()}",
            )
        return ToolResult(ok=True, content=stdout)

    @tool(
        name="kubectl_logs",
        description=(
            f"Fetch the logs of a pod (and optionally a specific container). "
            f"Context is locked to {config.context!r}. Namespace is "
            f"{ns_help}. Returns up to {config.max_log_lines} lines."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pod": {"type": "string"},
                "container": {"type": "string"},
                "namespace": {"type": "string"},
                "tail": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": config.max_log_lines,
                    "default": 200,
                },
                "since": {
                    "type": "string",
                    "description": "e.g. '5m', '1h', '2h30m'",
                },
                "previous": {
                    "type": "boolean",
                    "default": False,
                    "description": "Logs from the previous container instance",
                },
            },
            "required": ["pod"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def kubectl_logs(args: dict) -> ToolResult:
        name_err = _validate_name(args["pod"])
        if name_err:
            return ToolResult(ok=False, content=name_err)
        if args.get("container") and (
            err := _validate_name(args["container"])
        ):
            return ToolResult(ok=False, content=err)

        namespace, ns_err = _resolve_namespace(config, args.get("namespace"))
        if ns_err:
            return ToolResult(ok=False, content=ns_err)

        tail = min(int(args.get("tail", 200)), config.max_log_lines)
        extra: list[str] = [args["pod"], f"--tail={tail}"]
        if args.get("container"):
            extra += ["-c", args["container"]]
        if args.get("since"):
            # Validate since against a tight regex to avoid arg injection
            import re

            if not re.match(r"^\d+(s|m|h)(\d+(s|m|h))?$", args["since"]):
                return ToolResult(
                    ok=False, content=f"invalid since value: {args['since']!r}"
                )
            extra += [f"--since={args['since']}"]
        if args.get("previous"):
            extra.append("--previous")

        argv = _build_argv(config, "logs", *extra, namespace=namespace)
        rc, stdout, stderr = _run(argv, config.timeout_s)
        if rc != 0:
            return ToolResult(
                ok=False,
                content=f"kubectl logs failed (exit {rc}): {stderr.strip()}",
            )
        return ToolResult(
            ok=True,
            content=stdout,
            metadata={"pod": args["pod"], "tail": tail},
        )

    return [kubectl_get, kubectl_describe, kubectl_logs]
