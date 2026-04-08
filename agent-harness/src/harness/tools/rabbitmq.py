"""RabbitMQ management tools.

One read-only tool wrapping the RabbitMQ Management HTTP API:

- `rabbitmq_overview`  — cluster overview + queue listing with depths

The Management API (port 15672 by default) must be enabled on the broker.

Configuration (in the profile YAML):

    ops_tools:
      rabbitmq:
        enabled: true
        base_url: http://rabbitmq.example.com:15672
        user_env: RABBITMQ_USER          # defaults to 'guest'
        password_env: RABBITMQ_PASSWORD
        vhost: /                         # url-encoded as %2F by httpx
        timeout_s: 30
        max_queues: 100

Credentials are loaded from environment variables, never stored in config.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote as urlquote

import httpx

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class RabbitMQConfig:
    enabled: bool = False
    base_url: str = ""
    user: str = "guest"
    password: str = "guest"
    vhost: str = "/"
    timeout_s: int = 30
    max_queues: int = 100

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RabbitMQConfig:
        user_env = data.get("user_env", "RABBITMQ_USER")
        password_env = data.get("password_env", "RABBITMQ_PASSWORD")
        user = os.environ.get(user_env, "guest")
        password = os.environ.get(password_env, "guest")
        if data.get("enabled") and password == "guest":
            logger.warning(
                "rabbitmq enabled but %s is not set; using default credentials",
                password_env,
            )
        return cls(
            enabled=data.get("enabled", False),
            base_url=data.get("base_url", "").rstrip("/"),
            user=user,
            password=password,
            vhost=data.get("vhost", "/"),
            timeout_s=int(data.get("timeout_s", 30)),
            max_queues=int(data.get("max_queues", 100)),
        )


def build_rabbitmq_tools(config: RabbitMQConfig) -> list[Tool]:
    """Build the RabbitMQ tool from a config.

    Returns an empty list if rabbitmq is not enabled, so callers can
    blindly extend the registry.
    """
    if not config.enabled:
        return []
    if not config.base_url:
        logger.warning("rabbitmq enabled but base_url is empty; skipping")
        return []

    client = httpx.Client(
        base_url=config.base_url,
        auth=(config.user, config.password),
        timeout=config.timeout_s,
        headers={"Accept": "application/json"},
    )

    @tool(
        name="rabbitmq_overview",
        description=(
            "Get RabbitMQ cluster overview and queue listing. Returns cluster "
            "name, Erlang/RabbitMQ versions, message rates, and a list of "
            "queues with their message count, consumer count, and state. "
            "Use this to check broker health, detect queue backlogs, or find "
            "dead-letter queues with accumulated messages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "vhost": {
                    "type": "string",
                    "description": (
                        "Virtual host to list queues for (default: profile vhost)"
                    ),
                },
                "name_filter": {
                    "type": "string",
                    "description": (
                        "Optional substring filter on queue names (case-insensitive)"
                    ),
                },
            },
        },
        risk="safe",
        side_effects={"network", "read"},
    )
    def rabbitmq_overview(args: dict) -> ToolResult:
        vhost = args.get("vhost", config.vhost)
        name_filter = args.get("name_filter", "").lower()
        vhost_encoded = urlquote(vhost, safe="")

        # Fetch overview
        try:
            overview_resp = client.get("/api/overview")
            overview_resp.raise_for_status()
            overview = overview_resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"rabbitmq overview request failed: {exc}"
            )

        # Fetch queues
        try:
            queues_resp = client.get(
                f"/api/queues/{vhost_encoded}",
                params={"page_size": config.max_queues, "page": 1},
            )
            queues_resp.raise_for_status()
            queues_data = queues_resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                ok=False, content=f"rabbitmq queues request failed: {exc}"
            )

        # Handle paginated vs direct response
        if isinstance(queues_data, dict):
            queues = queues_data.get("items", [])
        else:
            queues = queues_data[:config.max_queues]

        # Apply name filter
        if name_filter:
            queues = [q for q in queues if name_filter in q.get("name", "").lower()]

        # Build overview section
        msg_stats = overview.get("message_stats", {})
        queue_totals = overview.get("queue_totals", {})
        lines = [
            f"Cluster: {overview.get('cluster_name', '?')}",
            f"RabbitMQ: {overview.get('rabbitmq_version', '?')} / "
            f"Erlang: {overview.get('erlang_version', '?')}",
            f"Messages ready: {queue_totals.get('messages_ready', 0)}",
            f"Messages unacked: {queue_totals.get('messages_unacknowledged', 0)}",
            f"Publish rate: {msg_stats.get('publish_details', {}).get('rate', 0):.1f}/s",
            f"Deliver rate: {msg_stats.get('deliver_get_details', {}).get('rate', 0):.1f}/s",
            "",
            f"Queues ({len(queues)} on vhost {vhost}):",
            "name\tmessages\tconsumers\tstate",
        ]
        for q in queues:
            lines.append(
                f"{q.get('name', '?')}\t"
                f"{q.get('messages', 0)}\t"
                f"{q.get('consumers', 0)}\t"
                f"{q.get('state', '?')}"
            )

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={"queue_count": len(queues), "vhost": vhost},
        )

    return [rabbitmq_overview]
