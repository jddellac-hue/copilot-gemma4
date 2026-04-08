"""Eval suite runner.

Iterates over `eval/tasks/*.yaml`, sets up an isolated workspace fixture
for each task, runs the agent, and verifies the success criterion. Produces
a JSON report and a non-zero exit code if any task fails.

Usage:
    harness eval --profile config/profiles/ci.yaml
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _setup_fixture(workspace: Path, fixture: dict[str, Any]) -> None:
    for relpath, content in fixture.get("files", {}).items():
        target = workspace / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _check_success(
    success: dict[str, Any], answer: str, workspace: Path
) -> tuple[bool, str]:
    kind = success["type"]
    if kind == "contains":
        expected = success["expected"]
        case_sensitive = success.get("case_sensitive", True)
        haystack = answer if case_sensitive else answer.lower()
        needle = expected if case_sensitive else expected.lower()
        ok = needle in haystack
        return ok, f"contains check: expected={expected!r} found={ok}"
    if kind == "exact":
        ok = answer.strip() == success["expected"].strip()
        return ok, f"exact check: ok={ok}"
    if kind == "bash":
        proc = subprocess.run(  # noqa: S602
            success["command"],
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc.returncode == 0, (
            f"bash check exit={proc.returncode} stderr={proc.stderr[:200]}"
        )
    return False, f"unknown success type: {kind}"


def _run_one_task(
    task: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Run a single eval task in an isolated tmp workspace."""
    # Imported lazily so the runner doesn't pull the full agent stack
    # when only used for listing/inspecting tasks.
    from harness.cli import _build_agent

    task_id = task["id"]
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix=f"eval-{task_id}-") as tmp:
        workspace = Path(tmp)
        _setup_fixture(workspace, task.get("fixture", {}))

        # Override budgets if the task specifies them
        budget = task.get("budget", {})
        profile_copy = json.loads(json.dumps(profile))  # cheap deep copy
        profile_copy.setdefault("agent", {})
        multiplier = float(
            profile_copy.get("eval", {}).get("budget_multiplier", 1.0)
        )
        if "max_steps" in budget:
            profile_copy["agent"]["max_steps"] = int(
                budget["max_steps"] * multiplier
            )
        if "max_tokens" in budget:
            profile_copy["agent"]["token_budget"] = int(
                budget["max_tokens"] * multiplier
            )

        # In CI mode the confirm callback should never be invoked because
        # there are no `ask` decisions in the ci profile.
        agent = _build_agent(profile_copy, workspace)

        try:
            answer = agent.run(task["prompt"])
            error: str | None = None
        except Exception as exc:  # noqa: BLE001
            answer = ""
            error = f"{type(exc).__name__}: {exc}"

        # Persist the final answer for bash success checks that may want it
        (workspace / "..").resolve()
        try:
            Path("/tmp/agent-eval-final.txt").write_text(answer, encoding="utf-8")
        except OSError:
            pass

        if error:
            ok, detail = False, f"agent raised: {error}"
        else:
            ok, detail = _check_success(task["success"], answer, workspace)

        duration_s = round(time.monotonic() - started, 2)

    return {
        "id": task_id,
        "category": task.get("category", "uncategorised"),
        "ok": ok,
        "detail": detail,
        "duration_s": duration_s,
        "answer_preview": (answer or "")[:200],
    }


def run_suite(
    profile: dict[str, Any], tasks_dir: Path, report_path: Path
) -> int:
    """Run all tasks in `tasks_dir`. Returns the process exit code."""
    tasks_dir = tasks_dir.resolve()
    if not tasks_dir.is_dir():
        logger.error("tasks dir not found: %s", tasks_dir)
        return 2

    task_files = sorted(tasks_dir.glob("*.yaml"))
    results: list[dict[str, Any]] = []

    for tf in task_files:
        with tf.open(encoding="utf-8") as f:
            task = yaml.safe_load(f)
        logger.info("running task %s", task["id"])
        try:
            results.append(_run_one_task(task, profile))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": task["id"],
                    "category": task.get("category", "uncategorised"),
                    "ok": False,
                    "detail": f"runner crashed: {exc}",
                    "duration_s": 0,
                }
            )

    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("eval summary: %d/%d passed", passed, len(results))

    # Print a human-readable table to stdout
    print("\n=== Eval results ===")
    for r in results:
        marker = "✓" if r["ok"] else "✗"
        print(f"  {marker} {r['id']:<35} {r['category']:<14} {r['duration_s']}s")
    print(f"\n  total: {passed}/{len(results)} passed")

    return 0 if failed == 0 else 1
