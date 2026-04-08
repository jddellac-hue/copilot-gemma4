"""Dynatrace tools.

Four read-only tools wired on the Dynatrace API:

- `dynatrace_dql`            — execute a DQL query on Grail
- `dynatrace_problems`       — list currently open or recent problems
- `dynatrace_entity_search`  — search monitored entities by selector
- `sre_slo_status`           — list SLOs with error budget and compliance

All tools are classified as `safe` with side effects `{network, read}`.
They are intended for the `ops` / `prod-ro` profiles.

Configuration (in the profile YAML):

    ops_tools:
      dynatrace:
        enabled: true
        tenant_url: https://<tenant>.live.dynatrace.com  # or .apps for Grail
        token_env: DT_API_TOKEN             # env var holding the token
        dql_endpoint: /platform/storage/query/v1/query:execute
        problems_endpoint: /api/v2/problems
        entities_endpoint: /api/v2/entities
        default_time_range: "now-1h"
        timeout_s: 30

The two endpoint styles supported:

- Classic v2 API (`/api/v2/...`) uses a simple GET/POST, results returned
  in one shot.
- Grail DQL (`/platform/storage/query/v1/query:execute`) uses an async
  submit/poll pattern: submit the query, get a request_token, then poll
  `/query:poll?request-token=...` until the `state` is SUCCEEDED.

The code handles both — the DQL tool auto-detects the pattern based on
whether the response contains `requestToken` vs direct `records`.

Endpoints evolve; if your tenant uses different paths, override them in
the profile. You should not need to modify this module.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class DynatraceConfig:
    enabled: bool = False
    tenant_url: str = ""
    token: str = ""
    dql_endpoint: str = "/platform/storage/query/v1/query:execute"
    dql_poll_endpoint: str = "/platform/storage/query/v1/query:poll"
    problems_endpoint: str = "/api/v2/problems"
    entities_endpoint: str = "/api/v2/entities"
    slo_endpoint: str = "/api/v2/slo"
    default_time_range: str = "now-1h"
    timeout_s: int = 30
    max_rows: int = 1000
    max_poll_attempts: int = 20
    poll_interval_s: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DynatraceConfig:
        token_env = data.get("token_env", "DT_API_TOKEN")
        token = os.environ.get(token_env, "")
        if data.get("enabled") and not token:
            logger.warning(
                "dynatrace enabled but env var %s is empty; tool calls will fail",
                token_env,
            )
        return cls(
            enabled=data.get("enabled", False),
            tenant_url=data.get("tenant_url", "").rstrip("/"),
            token=token,
            dql_endpoint=data.get(
                "dql_endpoint", "/platform/storage/query/v1/query:execute"
            ),
            dql_poll_endpoint=data.get(
                "dql_poll_endpoint", "/platform/storage/query/v1/query:poll"
            ),
            problems_endpoint=data.get("problems_endpoint", "/api/v2/problems"),
            entities_endpoint=data.get("entities_endpoint", "/api/v2/entities"),
            slo_endpoint=data.get("slo_endpoint", "/api/v2/slo"),
            default_time_range=data.get("default_time_range", "now-1h"),
            timeout_s=int(data.get("timeout_s", 30)),
            max_rows=int(data.get("max_rows", 1000)),
        )


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Api-Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def build_dynatrace_tools(config: DynatraceConfig) -> list[Tool]:
    """Build the three Dynatrace tools from a config.

    Returns an empty list if dynatrace is not enabled, so callers can
    blindly extend the registry.
    """
    if not config.enabled:
        return []
    if not config.tenant_url:
        logger.warning("dynatrace enabled but tenant_url is empty; skipping")
        return []

    client = httpx.Client(
        base_url=config.tenant_url,
        headers=_auth_headers(config.token),
        timeout=config.timeout_s,
    )

    @tool(
        name="dynatrace_dql",
        description=(
            "Execute a Dynatrace Query Language (DQL) query against Grail. "
            "Returns up to 1000 rows. The query should be a valid DQL "
            "statement, for example: "
            "`fetch logs | filter contains(content, \"OutOfMemory\") | limit 20` "
            "or "
            "`timeseries cpu = avg(dt.host.cpu.usage), by: {host.name}`. "
            "Use this tool for any metric, log, event or trace query. Do NOT "
            "include a trailing semicolon."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The DQL query"},
                "time_range": {
                    "type": "string",
                    "description": (
                        "Relative time range like 'now-1h', 'now-24h', "
                        "'now-7d'. Defaults to the profile default."
                    ),
                },
            },
            "required": ["query"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def dynatrace_dql(args: dict) -> ToolResult:
        query = args["query"]
        time_range = args.get("time_range", config.default_time_range)
        payload = {
            "query": query,
            "defaultTimeframeStart": time_range,
            "defaultTimeframeEnd": "now",
            "maxResultRecords": config.max_rows,
        }
        try:
            resp = client.post(config.dql_endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"dynatrace DQL request failed: {exc}"
            )

        # Grail async pattern: if we got a requestToken, poll until done
        if "requestToken" in data and "result" not in data:
            token = data["requestToken"]
            for _attempt in range(config.max_poll_attempts):
                time.sleep(config.poll_interval_s)
                try:
                    poll = client.get(
                        config.dql_poll_endpoint,
                        params={"request-token": token},
                    )
                    poll.raise_for_status()
                    polled = poll.json()
                except httpx.HTTPError as exc:
                    return ToolResult(
                        ok=False, content=f"dynatrace DQL poll failed: {exc}"
                    )
                state = polled.get("state", "")
                if state == "SUCCEEDED":
                    data = polled
                    break
                if state in ("FAILED", "CANCELLED"):
                    return ToolResult(
                        ok=False,
                        content=f"dynatrace DQL state={state}: {polled}",
                    )
            else:
                return ToolResult(
                    ok=False,
                    content="dynatrace DQL polling exhausted without result",
                )

        records = data.get("result", {}).get("records", data.get("records", []))
        if not records:
            return ToolResult(
                ok=True,
                content="[no records returned]",
                metadata={"row_count": 0, "query": query},
            )

        # Render as a compact text table: header line + rows as TSV
        columns = list(records[0].keys())
        lines = ["\t".join(columns)]
        for row in records[: config.max_rows]:
            lines.append("\t".join(str(row.get(c, "")) for c in columns))
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"row_count": len(records), "query": query},
        )

    @tool(
        name="dynatrace_problems",
        description=(
            "List Dynatrace problems (incidents detected by the AI engine). "
            "Returns up to 50 problems for the given time range, with "
            "severity, impact level, affected entities, and problem ID. Use "
            "for a quick 'what's on fire' overview."
        ),
        parameters={
            "type": "object",
            "properties": {
                "time_range": {
                    "type": "string",
                    "description": "e.g. 'now-2h', 'now-24h' (default: now-1h)",
                },
                "status": {
                    "type": "string",
                    "enum": ["OPEN", "CLOSED", "ALL"],
                    "default": "OPEN",
                },
                "severity": {
                    "type": "string",
                    "enum": [
                        "AVAILABILITY",
                        "ERROR",
                        "PERFORMANCE",
                        "RESOURCE_CONTENTION",
                        "CUSTOM_ALERT",
                        "MONITORING_UNAVAILABLE",
                        "INFO",
                        "ALL",
                    ],
                    "default": "ALL",
                },
            },
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def dynatrace_problems(args: dict) -> ToolResult:
        time_range = args.get("time_range", config.default_time_range)
        status = args.get("status", "OPEN")
        severity = args.get("severity", "ALL")

        selectors: list[str] = []
        if status != "ALL":
            selectors.append(f'status("{status}")')
        if severity != "ALL":
            selectors.append(f'severityLevel("{severity}")')
        problem_selector = ",".join(selectors) if selectors else None

        params = {
            "from": time_range,
            "to": "now",
            "pageSize": 50,
        }
        if problem_selector:
            params["problemSelector"] = problem_selector

        try:
            resp = client.get(config.problems_endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"dynatrace problems request failed: {exc}"
            )

        problems = data.get("problems", [])
        if not problems:
            return ToolResult(ok=True, content="[no problems in range]")

        lines = []
        for p in problems:
            entities = ",".join(
                e.get("name", "?") for e in p.get("affectedEntities", [])
            )
            lines.append(
                f"{p.get('problemId', '?')}\t"
                f"{p.get('status', '?')}\t"
                f"{p.get('severityLevel', '?')}\t"
                f"{p.get('impactLevel', '?')}\t"
                f"{p.get('title', '?')}\t"
                f"entities={entities}"
            )
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"problem_count": len(problems)},
        )

    @tool(
        name="dynatrace_entity_search",
        description=(
            "Search monitored entities in Dynatrace using an entity selector. "
            "Examples: `type(HOST)`, `type(KUBERNETES_CLUSTER)`, "
            "`type(SERVICE),tag(env:prod)`, `entityName.contains(billing)`. "
            "Returns up to 100 entities with their displayName and entityId."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_selector": {
                    "type": "string",
                    "description": "A Dynatrace entity selector expression",
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "Optional comma-separated extra fields to include "
                        "(e.g. 'properties.ipAddress,fromRelationships')"
                    ),
                },
            },
            "required": ["entity_selector"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def dynatrace_entity_search(args: dict) -> ToolResult:
        params = {
            "entitySelector": args["entity_selector"],
            "pageSize": 100,
            "from": config.default_time_range,
            "to": "now",
        }
        if args.get("fields"):
            params["fields"] = args["fields"]

        try:
            resp = client.get(config.entities_endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"dynatrace entity search failed: {exc}"
            )

        entities = data.get("entities", [])
        if not entities:
            return ToolResult(ok=True, content="[no entities matched]")

        lines = []
        for e in entities:
            lines.append(
                f"{e.get('entityId', '?')}\t"
                f"{e.get('displayName', '?')}\t"
                f"type={e.get('type', '?')}"
            )
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"entity_count": len(entities)},
        )

    @tool(
        name="sre_slo_status",
        description=(
            "List all SLOs (Service Level Objectives) from Dynatrace with "
            "their current compliance status, error budget remaining, and "
            "burn rate. Use this to check SRE health: which SLOs are at risk, "
            "which have exhausted their error budget, and overall service "
            "reliability posture. Returns name, target, evaluated percentage, "
            "status, and error budget for each SLO."
        ),
        parameters={
            "type": "object",
            "properties": {
                "time_range": {
                    "type": "string",
                    "description": (
                        "Time frame for SLO evaluation: 'now-1h', 'now-24h', "
                        "'now-7d', 'now-30d' (default: now-24h)"
                    ),
                },
                "name_filter": {
                    "type": "string",
                    "description": (
                        "Optional substring filter on SLO names (case-insensitive)"
                    ),
                },
                "status_filter": {
                    "type": "string",
                    "enum": ["WARNING", "FAILURE", "SUCCESS", "ALL"],
                    "description": "Filter by SLO status (default: ALL)",
                },
            },
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def sre_slo_status(args: dict) -> ToolResult:
        time_range = args.get("time_range", "now-24h")
        name_filter = args.get("name_filter", "").lower()
        status_filter = args.get("status_filter", "ALL")

        params = {
            "pageSize": 200,
            "from": time_range,
            "to": "now",
            "evaluate": "true",
        }
        try:
            resp = client.get(config.slo_endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"dynatrace SLO request failed: {exc}"
            )

        slos = data.get("slo", [])
        if not slos:
            return ToolResult(ok=True, content="[no SLOs configured]")

        # Apply filters
        if name_filter:
            slos = [s for s in slos if name_filter in s.get("name", "").lower()]
        if status_filter != "ALL":
            slos = [s for s in slos if s.get("status") == status_filter]

        if not slos:
            return ToolResult(ok=True, content="[no SLOs match filters]")

        lines = [
            f"SLOs ({len(slos)}) — evaluated over {time_range}",
            "",
            "name\tstatus\ttarget\tevaluated\terror_budget",
        ]
        for s in slos:
            evaluated = s.get("evaluatedPercentage", 0)
            target = s.get("target", 0)
            error_budget = s.get("errorBudget", 0)
            lines.append(
                f"{s.get('name', '?')}\t"
                f"{s.get('status', '?')}\t"
                f"{target:.2f}%\t"
                f"{evaluated:.2f}%\t"
                f"{error_budget:.2f}%"
            )

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"slo_count": len(slos), "time_range": time_range},
        )

    return [dynatrace_dql, dynatrace_problems, dynatrace_entity_search, sre_slo_status]
