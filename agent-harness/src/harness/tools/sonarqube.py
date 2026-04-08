"""SonarQube tools.

Two read-only tools for querying SonarQube quality data:

- `sonarqube_quality_gate`  — get the quality gate status of a project
- `sonarqube_issues`        — search issues by severity/type for a component

Both are classified as `safe` with side effects `{network, read}`.

Configuration (in the profile YAML):

    ops_tools:
      sonarqube:
        enabled: true
        base_url: https://sonar.example.com
        token_env: SONAR_TOKEN
        timeout_s: 30
        max_issues: 50

The token needs only "Browse" permission on the target projects. It is
loaded from an environment variable, never stored in config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class SonarQubeConfig:
    enabled: bool = False
    base_url: str = ""
    token: str = ""
    timeout_s: int = 30
    max_issues: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SonarQubeConfig:
        token_env = data.get("token_env", "SONAR_TOKEN")
        token = os.environ.get(token_env, "")
        if data.get("enabled") and not token:
            logger.warning(
                "sonarqube enabled but env var %s is empty; tool calls will fail",
                token_env,
            )
        return cls(
            enabled=data.get("enabled", False),
            base_url=data.get("base_url", "").rstrip("/"),
            token=token,
            timeout_s=int(data.get("timeout_s", 30)),
            max_issues=int(data.get("max_issues", 50)),
        )


def build_sonarqube_tools(config: SonarQubeConfig) -> list[Tool]:
    """Build the two SonarQube tools from a config.

    Returns an empty list if sonarqube is not enabled, so callers can
    blindly extend the registry.
    """
    if not config.enabled:
        return []
    if not config.base_url:
        logger.warning("sonarqube enabled but base_url is empty; skipping")
        return []

    client = httpx.Client(
        base_url=config.base_url,
        auth=(config.token, ""),  # SonarQube token-as-username, no password
        timeout=config.timeout_s,
        headers={"Accept": "application/json"},
    )

    @tool(
        name="sonarqube_quality_gate",
        description=(
            "Get the quality gate status for a SonarQube project. Returns "
            "the overall status (OK, WARN, ERROR) and the status of each "
            "condition (coverage, duplications, reliability, security, etc.). "
            "Use this to check if a project passes quality criteria before "
            "release or to investigate why a quality gate is failing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": (
                        "The SonarQube project key (e.g. 'com.example:my-app')"
                    ),
                },
                "branch": {
                    "type": "string",
                    "description": (
                        "Optional branch name (defaults to the main branch)"
                    ),
                },
            },
            "required": ["project_key"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def sonarqube_quality_gate(args: dict) -> ToolResult:
        params: dict[str, Any] = {"projectKey": args["project_key"]}
        if args.get("branch"):
            params["branch"] = args["branch"]

        try:
            resp = client.get("/api/qualitygates/project_status", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"sonarqube quality gate request failed: {exc}"
            )

        status = data.get("projectStatus", {})
        overall = status.get("status", "UNKNOWN")
        conditions = status.get("conditions", [])

        lines = [f"Quality Gate: {overall}"]
        if conditions:
            lines.append("")
            lines.append("metric\tstatus\tvalue\terror_threshold")
            for c in conditions:
                lines.append(
                    f"{c.get('metricKey', '?')}\t"
                    f"{c.get('status', '?')}\t"
                    f"{c.get('actualValue', '?')}\t"
                    f"{c.get('errorThreshold', '-')}"
                )

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"status": overall, "project_key": args["project_key"]},
        )

    @tool(
        name="sonarqube_issues",
        description=(
            "Search SonarQube issues (bugs, vulnerabilities, code smells, "
            "security hotspots) for a project. Filter by severity and type. "
            "Returns up to 50 issues with file location, message, and effort. "
            "Use this to understand code quality problems or investigate "
            "security vulnerabilities flagged by SonarQube."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "The SonarQube project key",
                },
                "types": {
                    "type": "string",
                    "description": (
                        "Comma-separated issue types: BUG, VULNERABILITY, "
                        "CODE_SMELL, SECURITY_HOTSPOT (default: all)"
                    ),
                },
                "severities": {
                    "type": "string",
                    "description": (
                        "Comma-separated severities: BLOCKER, CRITICAL, "
                        "MAJOR, MINOR, INFO (default: all)"
                    ),
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch name",
                },
                "statuses": {
                    "type": "string",
                    "description": (
                        "Comma-separated statuses: OPEN, CONFIRMED, "
                        "REOPENED, RESOLVED, CLOSED (default: OPEN)"
                    ),
                },
            },
            "required": ["project_key"],
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def sonarqube_issues(args: dict) -> ToolResult:
        params: dict[str, Any] = {
            "componentKeys": args["project_key"],
            "ps": config.max_issues,
            "statuses": args.get("statuses", "OPEN"),
        }
        if args.get("types"):
            params["types"] = args["types"]
        if args.get("severities"):
            params["severities"] = args["severities"]
        if args.get("branch"):
            params["branch"] = args["branch"]

        try:
            resp = client.get("/api/issues/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"sonarqube issues request failed: {exc}"
            )

        total = data.get("total", 0)
        issues = data.get("issues", [])

        if not issues:
            return ToolResult(
                ok=True,
                content="[no issues found]",
                metadata={"total": 0},
            )

        lines = [f"Total: {total} issues (showing {len(issues)})"]
        lines.append("")
        lines.append("severity\ttype\tcomponent\tline\tmessage")
        for issue in issues:
            component = issue.get("component", "?").split(":")[-1]
            lines.append(
                f"{issue.get('severity', '?')}\t"
                f"{issue.get('type', '?')}\t"
                f"{component}\t"
                f"{issue.get('line', '-')}\t"
                f"{issue.get('message', '?')}"
            )

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"total": total, "returned": len(issues)},
        )

    return [sonarqube_quality_gate, sonarqube_issues]
