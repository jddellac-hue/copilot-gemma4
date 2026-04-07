"""Unit tests for the permission policy."""

from __future__ import annotations

from harness.permissions import PermissionPolicy


def test_default_decision_when_no_rule_matches():
    policy = PermissionPolicy.from_dict(
        "test", {"default": "ask", "rules": []}
    )
    assert policy.check("unknown_tool", {}) == "ask"


def test_explicit_allow_rule():
    policy = PermissionPolicy.from_dict(
        "test",
        {
            "default": "deny",
            "rules": [{"tool": "read_file", "decision": "allow"}],
        },
    )
    assert policy.check("read_file", {"path": "foo.txt"}) == "allow"
    assert policy.check("write_file", {"path": "foo.txt"}) == "deny"


def test_deny_pattern_overrides_allow():
    policy = PermissionPolicy.from_dict(
        "test",
        {
            "default": "deny",
            "rules": [
                {
                    "tool": "bash",
                    "decision": "allow",
                    "patterns_deny": ["rm\\s+-rf"],
                }
            ],
        },
    )
    assert policy.check("bash", {"command": "ls -la"}) == "allow"
    assert policy.check("bash", {"command": "rm -rf /tmp/foo"}) == "deny"


def test_ask_pattern_downgrades_allow():
    policy = PermissionPolicy.from_dict(
        "test",
        {
            "default": "deny",
            "rules": [
                {
                    "tool": "bash",
                    "decision": "allow",
                    "patterns_ask": ["git\\s+push"],
                }
            ],
        },
    )
    assert policy.check("bash", {"command": "git status"}) == "allow"
    assert policy.check("bash", {"command": "git push origin main"}) == "ask"


def test_wildcard_rule():
    policy = PermissionPolicy.from_dict(
        "test",
        {
            "default": "allow",
            "rules": [
                {"tool": "read_file", "decision": "allow"},
                {"tool": "*", "decision": "ask"},
            ],
        },
    )
    assert policy.check("read_file", {}) == "allow"
    assert policy.check("anything_else", {}) == "ask"
