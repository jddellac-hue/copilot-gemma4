"""Unit tests for the Concourse SSE parser."""

from __future__ import annotations

from harness.tools.concourse import ConcourseConfig, _parse_sse


def test_parse_single_log_event():
    sse = (
        'event: log\n'
        'data: {"data":{"payload":"hello world"}}\n'
        '\n'
    )
    events = _parse_sse(sse)
    assert len(events) == 1
    assert events[0][0] == "log"
    assert events[0][1]["data"]["payload"] == "hello world"


def test_parse_multiple_events():
    sse = (
        'event: log\n'
        'data: {"data":{"payload":"line 1"}}\n'
        '\n'
        'event: log\n'
        'data: {"data":{"payload":"line 2"}}\n'
        '\n'
        'event: finish-task\n'
        'data: {"data":{"exit_status":0}}\n'
        '\n'
    )
    events = _parse_sse(sse)
    assert [e[0] for e in events] == ["log", "log", "finish-task"]


def test_parse_skips_malformed_records():
    sse = (
        'event: log\n'
        'data: not json\n'
        '\n'
        'event: log\n'
        'data: {"data":{"payload":"valid"}}\n'
        '\n'
    )
    events = _parse_sse(sse)
    assert len(events) == 1
    assert events[0][1]["data"]["payload"] == "valid"


def test_parse_skips_records_without_event_or_data():
    sse = (
        ': comment line\n'
        '\n'
        'event: log\n'
        '\n'
        'data: {}\n'
        '\n'
    )
    events = _parse_sse(sse)
    assert events == []


def test_concourse_config_defaults():
    cfg = ConcourseConfig.from_dict({})
    assert cfg.enabled is False
    assert cfg.team == "main"
    assert cfg.timeout_s == 30
