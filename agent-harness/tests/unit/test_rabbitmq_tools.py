"""Unit tests for the RabbitMQ tools.

These tests do NOT call RabbitMQ. They verify config parsing
and build/disable logic.
"""

from __future__ import annotations

from harness.tools.rabbitmq import RabbitMQConfig, build_rabbitmq_tools


def test_build_returns_empty_when_disabled():
    tools = build_rabbitmq_tools(RabbitMQConfig(enabled=False))
    assert tools == []


def test_build_returns_empty_when_no_base_url():
    tools = build_rabbitmq_tools(RabbitMQConfig(enabled=True, base_url=""))
    assert tools == []


def test_build_returns_one_tool_when_enabled():
    tools = build_rabbitmq_tools(
        RabbitMQConfig(
            enabled=True,
            base_url="http://rabbitmq.example.com:15672",
            user="admin",
            password="secret",
        )
    )
    names = [t.name for t in tools]
    assert names == ["rabbitmq_overview"]


def test_tool_is_safe():
    tools = build_rabbitmq_tools(
        RabbitMQConfig(
            enabled=True,
            base_url="http://rabbitmq.example.com:15672",
        )
    )
    for t in tools:
        assert t.risk == "safe"
        assert "network" in t.side_effects
        assert "read" in t.side_effects


def test_config_from_dict():
    import os

    os.environ["RMQ_U"] = "myuser"
    os.environ["RMQ_P"] = "mypass"
    try:
        cfg = RabbitMQConfig.from_dict({
            "enabled": True,
            "base_url": "http://rmq:15672/",
            "user_env": "RMQ_U",
            "password_env": "RMQ_P",
            "vhost": "production",
            "timeout_s": 15,
            "max_queues": 200,
        })
        assert cfg.enabled is True
        assert cfg.base_url == "http://rmq:15672"
        assert cfg.user == "myuser"
        assert cfg.password == "mypass"
        assert cfg.vhost == "production"
        assert cfg.timeout_s == 15
        assert cfg.max_queues == 200
    finally:
        del os.environ["RMQ_U"]
        del os.environ["RMQ_P"]
