"""Concourse CI tools.

Three read-only tools wrapping the Concourse v1 API:

- `concourse_pipelines`   — list pipelines for a team
- `concourse_builds`      — recent builds for a pipeline (and optional job)
- `concourse_build_logs`  — fetch the log events for a build

The Concourse log API is event-stream-based (SSE). We consume the stream,
filter `log` events, and assemble them into plain text. Other event types
(initialize, start, finish) are summarised at the end.

Configuration:

    ops_tools:
      concourse:
        enabled: true
        base_url: https://concourse.example.com
        team: main
        token_env: CONCOURSE_TOKEN     # bearer token
        timeout_s: 30
        max_log_chars: 32768

The bearer token can be obtained via `fly login -t <target>` and then
extracted from `~/.flyrc`, or directly via the Concourse OAuth flow. We
do not handle login from the harness — that's an operator concern.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class ConcourseConfig:
    enabled: bool = False
    base_url: str = ""
    team: str = "main"
    token: str = ""
    timeout_s: int = 30
    max_log_chars: int = 32768
    max_builds: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConcourseConfig:
        token_env = data.get("token_env", "CONCOURSE_TOKEN")
        token = os.environ.get(token_env, "")
        if data.get("enabled") and not token:
            logger.warning(
                "concourse enabled but env var %s is empty; tool calls will fail",
                token_env,
            )
        return cls(
            enabled=data.get("enabled", False),
            base_url=data.get("base_url", "").rstrip("/"),
            team=data.get("team", "main"),
            token=token,
            timeout_s=int(data.get("timeout_s", 30)),
            max_log_chars=int(data.get("max_log_chars", 32768)),
            max_builds=int(data.get("max_builds", 50)),
        )


def _parse_sse(stream_text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse a Server-Sent Events payload into [(event, data_dict), ...].

    Each SSE record is delimited by a blank line. Within a record, lines
    are `field: value`. We only care about `event` and `data`.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    for record in stream_text.split("\n\n"):
        event_type = ""
        data_str = ""
        for line in record.splitlines():
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if not event_type or not data_str:
            continue
        try:
            data_obj = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        events.append((event_type, data_obj))
    return events


def build_concourse_tools(config: ConcourseConfig) -> list[Tool]:
    """Build the Concourse tools, or return [] if not enabled."""
    if not config.enabled:
        return []
    if not config.base_url:
        logger.warning("concourse enabled but base_url is empty; skipping")
        return []

    client = httpx.Client(
        base_url=config.base_url,
        headers={
            "Authorization": f"Bearer {config.token}",
            "Accept": "application/json",
        },
        timeout=config.timeout_s,
    )

    @tool(
        name="concourse_pipelines",
        description=(
            f"List pipelines in the Concourse team {config.team!r}. Returns "
            "the pipeline name, paused status, and a link to the pipeline."
        ),
        parameters={
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": (
                        "Team name. Defaults to the profile-configured team."
                    ),
                },
            },
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def concourse_pipelines(args: dict) -> ToolResult:
        team = args.get("team", config.team)
        try:
            resp = client.get(f"/api/v1/teams/{team}/pipelines")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"concourse pipelines request failed: {exc}"
            )

        if not data:
            return ToolResult(ok=True, content=f"[no pipelines in team {team}]")

        lines = []
        for p in data:
            paused = "PAUSED" if p.get("paused") else "active"
            lines.append(
                f"{p.get('name', '?')}\t{paused}\t"
                f"{config.base_url}/teams/{team}/pipelines/{p.get('name', '?')}"
            )
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"pipeline_count": len(data), "team": team},
        )

    @tool(
        name="concourse_builds",
        description=(
            "List recent builds for a Concourse pipeline. If a job name is "
            "given, only that job's builds are returned. Each line shows: "
            "build_id, job, status (succeeded/failed/errored/aborted), "
            "started_at, duration."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pipeline": {"type": "string"},
                "job": {
                    "type": "string",
                    "description": "Optional job name within the pipeline",
                },
                "team": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": config.max_builds,
                    "default": 10,
                },
            },
            "required": ["pipeline"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def concourse_builds(args: dict) -> ToolResult:
        team = args.get("team", config.team)
        pipeline = args["pipeline"]
        limit = min(int(args.get("limit", 10)), config.max_builds)
        if args.get("job"):
            url = (
                f"/api/v1/teams/{team}/pipelines/{pipeline}/jobs/"
                f"{args['job']}/builds"
            )
        else:
            url = f"/api/v1/teams/{team}/pipelines/{pipeline}/builds"

        try:
            resp = client.get(url, params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"concourse builds request failed: {exc}"
            )

        if not data:
            return ToolResult(ok=True, content="[no builds]")

        lines = []
        for b in data[:limit]:
            start = b.get("start_time", 0)
            end = b.get("end_time", 0)
            duration = (end - start) if (start and end) else 0
            lines.append(
                f"{b.get('id', '?')}\t"
                f"{b.get('job_name', '?')}\t"
                f"{b.get('status', '?')}\t"
                f"started={start}\t"
                f"duration={duration}s\t"
                f"name={b.get('name', '?')}"
            )
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"build_count": len(data), "pipeline": pipeline},
        )

    @tool(
        name="concourse_build_logs",
        description=(
            "Fetch the logs of a Concourse build by ID. Returns the log "
            "lines (truncated at 32 KiB by default) plus a final summary of "
            "step status. Use after `concourse_builds` has identified the "
            "interesting build."
        ),
        parameters={
            "type": "object",
            "properties": {
                "build_id": {
                    "type": "integer",
                    "description": "The numeric build id from concourse_builds",
                },
            },
            "required": ["build_id"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def concourse_build_logs(args: dict) -> ToolResult:
        build_id = int(args["build_id"])
        try:
            resp = client.get(
                f"/api/v1/builds/{build_id}/events",
                headers={"Accept": "text/event-stream"},
                timeout=config.timeout_s,
            )
            resp.raise_for_status()
            stream_text = resp.text
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"concourse log fetch failed: {exc}"
            )

        events = _parse_sse(stream_text)
        log_chunks: list[str] = []
        finishes: list[str] = []
        total_chars = 0

        for event_type, data in events:
            if event_type == "log":
                payload = data.get("data", {}).get("payload", "")
                if payload:
                    if total_chars + len(payload) > config.max_log_chars:
                        log_chunks.append(
                            f"\n[truncated at {config.max_log_chars} chars]"
                        )
                        break
                    log_chunks.append(payload)
                    total_chars += len(payload)
            elif event_type == "finish-task":
                step = data.get("data", {}).get("origin", {}).get("id", "?")
                code = data.get("data", {}).get("exit_status", "?")
                finishes.append(f"task {step}: exit={code}")
            elif event_type == "error":
                msg = data.get("data", {}).get("message", "?")
                finishes.append(f"ERROR: {msg}")

        body = "".join(log_chunks)
        if finishes:
            body += "\n\n--- step summary ---\n" + "\n".join(finishes)
        if not body:
            body = (
                "[no log events parsed — build may still be running, "
                "or stream format unsupported]"
            )
        return ToolResult(
            ok=True,
            content=body,
            metadata={"build_id": build_id, "log_chars": total_chars},
        )

    return [concourse_pipelines, concourse_builds, concourse_build_logs]
