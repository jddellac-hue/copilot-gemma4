"""Permission policy: allow / ask / deny decisions for tool calls.

Configurable via YAML. Each rule matches by tool name and optionally by
argument patterns. Decisions are logged to an immutable audit log.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

Decision = Literal["allow", "ask", "deny"]


@dataclass
class PermissionRule:
    tool: str
    decision: Decision
    arg_patterns_deny: list[str] = field(default_factory=list)
    arg_patterns_ask: list[str] = field(default_factory=list)


@dataclass
class PermissionPolicy:
    profile: str
    default: Decision
    rules: list[PermissionRule]
    audit_log_path: Path | None = None

    @classmethod
    def from_dict(cls, profile: str, data: dict[str, Any]) -> PermissionPolicy:
        rules = [
            PermissionRule(
                tool=r["tool"],
                decision=r["decision"],
                arg_patterns_deny=r.get("patterns_deny", []),
                arg_patterns_ask=r.get("patterns_ask", []),
            )
            for r in data.get("rules", [])
        ]
        audit_path = data.get("audit_log_path")
        return cls(
            profile=profile,
            default=data.get("default", "ask"),
            rules=rules,
            audit_log_path=Path(audit_path).expanduser() if audit_path else None,
        )

    def check(self, tool_name: str, arguments: dict[str, Any]) -> Decision:
        decision: Decision = self.default
        for rule in self.rules:
            if rule.tool != tool_name and rule.tool != "*":
                continue
            decision = rule.decision
            arg_blob = json.dumps(arguments, sort_keys=True)
            for pattern in rule.arg_patterns_deny:
                if re.search(pattern, arg_blob):
                    decision = "deny"
                    break
            else:
                for pattern in rule.arg_patterns_ask:
                    if re.search(pattern, arg_blob):
                        if decision == "allow":
                            decision = "ask"
                        break
            break
        self._audit(tool_name, arguments, decision)
        return decision

    def _audit(
        self, tool_name: str, arguments: dict[str, Any], decision: Decision
    ) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "profile": self.profile,
            "tool": tool_name,
            "args": arguments,
            "decision": decision,
        }
        logger.info("permission %s", json.dumps(record))
        if self.audit_log_path:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
