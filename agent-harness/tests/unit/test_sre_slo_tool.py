"""Unit tests for the sre_slo_status tool (in dynatrace module).

These tests do NOT call Dynatrace. They verify that the SLO tool
is built alongside the existing Dynatrace tools and validate arguments.
"""

from __future__ import annotations

from harness.tools.dynatrace import DynatraceConfig, build_dynatrace_tools


def test_build_returns_four_tools_when_enabled():
    tools = build_dynatrace_tools(
        DynatraceConfig(
            enabled=True,
            tenant_url="https://test.live.dynatrace.com",
            token="test-token",
        )
    )
    names = sorted(t.name for t in tools)
    assert names == [
        "dynatrace_dql",
        "dynatrace_entity_search",
        "dynatrace_problems",
        "sre_slo_status",
    ]


def test_sre_slo_tool_is_safe():
    tools = build_dynatrace_tools(
        DynatraceConfig(
            enabled=True,
            tenant_url="https://test.live.dynatrace.com",
            token="t",
        )
    )
    slo = next(t for t in tools if t.name == "sre_slo_status")
    assert slo.risk == "safe"
    assert "network" in slo.side_effects
    assert "read" in slo.side_effects


def test_slo_endpoint_in_config():
    cfg = DynatraceConfig.from_dict({
        "enabled": True,
        "tenant_url": "https://test.live.dynatrace.com",
        "token_env": "DT_API_TOKEN",
        "slo_endpoint": "/api/v2/slo/custom",
    })
    assert cfg.slo_endpoint == "/api/v2/slo/custom"


def test_slo_endpoint_default():
    cfg = DynatraceConfig.from_dict({
        "enabled": True,
        "tenant_url": "https://test.live.dynatrace.com",
    })
    assert cfg.slo_endpoint == "/api/v2/slo"


def test_sre_slo_accepts_empty_args():
    """sre_slo_status has no required params — empty dict should validate."""
    tools = build_dynatrace_tools(
        DynatraceConfig(
            enabled=True,
            tenant_url="https://test.live.dynatrace.com",
            token="t",
        )
    )
    slo = next(t for t in tools if t.name == "sre_slo_status")
    # invoke will fail on network (no real DT), but should not fail on
    # argument validation
    result = slo.invoke({})
    # Should fail with network error, not validation error
    assert not result.ok
    assert "request failed" in result.content or "raised an exception" in result.content
