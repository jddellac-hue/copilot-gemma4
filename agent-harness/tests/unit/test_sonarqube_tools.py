"""Unit tests for the SonarQube tools.

These tests do NOT call SonarQube. They verify config parsing
and build/disable logic.
"""

from __future__ import annotations

from harness.tools.sonarqube import SonarQubeConfig, build_sonarqube_tools


def test_build_returns_empty_when_disabled():
    tools = build_sonarqube_tools(SonarQubeConfig(enabled=False))
    assert tools == []


def test_build_returns_empty_when_no_base_url():
    tools = build_sonarqube_tools(SonarQubeConfig(enabled=True, base_url=""))
    assert tools == []


def test_build_returns_two_tools_when_enabled():
    tools = build_sonarqube_tools(
        SonarQubeConfig(
            enabled=True,
            base_url="https://sonar.example.com",
            token="test-token",
        )
    )
    names = sorted(t.name for t in tools)
    assert names == ["sonarqube_issues", "sonarqube_quality_gate"]


def test_all_tools_are_safe():
    tools = build_sonarqube_tools(
        SonarQubeConfig(
            enabled=True,
            base_url="https://sonar.example.com",
            token="t",
        )
    )
    for t in tools:
        assert t.risk == "safe"
        assert "network" in t.side_effects
        assert "read" in t.side_effects


def test_config_from_dict(monkeypatch: object):
    import os

    os.environ["MY_SONAR_TOKEN"] = "secret123"
    try:
        cfg = SonarQubeConfig.from_dict({
            "enabled": True,
            "base_url": "https://sonar.example.com/",
            "token_env": "MY_SONAR_TOKEN",
            "timeout_s": 60,
            "max_issues": 100,
        })
        assert cfg.enabled is True
        assert cfg.base_url == "https://sonar.example.com"  # trailing slash stripped
        assert cfg.token == "secret123"
        assert cfg.timeout_s == 60
        assert cfg.max_issues == 100
    finally:
        del os.environ["MY_SONAR_TOKEN"]


def test_quality_gate_rejects_missing_project_key():
    tools = build_sonarqube_tools(
        SonarQubeConfig(
            enabled=True,
            base_url="https://sonar.example.com",
            token="t",
        )
    )
    qg = next(t for t in tools if t.name == "sonarqube_quality_gate")
    result = qg.invoke({})
    assert not result.ok
    assert "project_key" in result.content


def test_issues_rejects_missing_project_key():
    tools = build_sonarqube_tools(
        SonarQubeConfig(
            enabled=True,
            base_url="https://sonar.example.com",
            token="t",
        )
    )
    issues = next(t for t in tools if t.name == "sonarqube_issues")
    result = issues.invoke({})
    assert not result.ok
    assert "project_key" in result.content
