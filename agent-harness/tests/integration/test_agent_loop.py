"""Integration test for the agent loop with a mocked Ollama model.

We replay scripted model responses to verify:
- Tool calls are dispatched and results re-injected
- Permission denials are surfaced as errors to the model
- Final answer is returned
- Repetition detection kicks in
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.agent import Agent, AgentConfig
from harness.memory import Memory
from harness.model import ModelResponse, ToolCall
from harness.observability import Observability
from harness.permissions import PermissionPolicy
from harness.tools import ToolRegistry, ToolResult, tool


class ScriptedModel:
    """Replays a fixed sequence of ModelResponse objects."""

    def __init__(self, model: str, responses: list[ModelResponse]):
        self.model = model
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> ModelResponse:
        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("scripted model exhausted")
        return self._responses.pop(0)


@pytest.fixture
def echo_tool():
    @tool(
        name="echo",
        description="Return the input text",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def _echo(args: dict) -> ToolResult:
        return ToolResult(ok=True, content=args["text"])

    return _echo


@pytest.fixture
def registry(echo_tool):
    r = ToolRegistry()
    r.register(echo_tool)
    return r


@pytest.fixture
def policy_allow_all():
    return PermissionPolicy.from_dict("test", {"default": "allow", "rules": []})


@pytest.fixture
def policy_deny_all():
    return PermissionPolicy.from_dict("test", {"default": "deny", "rules": []})


def _build_agent(model, registry, policy):
    return Agent(
        model=model,  # type: ignore[arg-type]
        tools=registry,
        permissions=policy,
        memory=Memory(system_prompt="test system"),
        observability=Observability(enabled=False),
        config=AgentConfig(max_steps=10, repetition_threshold=2),
    )


def test_simple_tool_call_then_answer(registry, policy_allow_all):
    model = ScriptedModel(
        "test",
        [
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="1", name="echo", arguments={"text": "hi"})],
            ),
            ModelResponse(content="The tool returned: hi"),
        ],
    )
    agent = _build_agent(model, registry, policy_allow_all)
    answer = agent.run("Echo hi for me")
    assert answer == "The tool returned: hi"
    assert len(model.calls) == 2


def test_permission_denied_is_surfaced(registry, policy_deny_all, monkeypatch):
    model = ScriptedModel(
        "test",
        [
            ModelResponse(
                content="",
                tool_calls=[ToolCall(id="1", name="echo", arguments={"text": "x"})],
            ),
            ModelResponse(content="I was denied, sorry"),
        ],
    )
    agent = _build_agent(model, registry, policy_deny_all)
    answer = agent.run("Try to echo")
    assert "denied" in answer.lower()
    # Verify the tool result message was injected with an error
    second_call_messages = model.calls[1]
    last_tool_msg = next(
        m for m in reversed(second_call_messages) if m.get("role") == "tool"
    )
    assert "permission denied" in last_tool_msg["content"].lower()


def test_repetition_detector(registry, policy_allow_all):
    repeat_call = ToolCall(id="1", name="echo", arguments={"text": "loop"})
    model = ScriptedModel(
        "test",
        [
            ModelResponse(content="", tool_calls=[repeat_call]),
            ModelResponse(content="", tool_calls=[repeat_call]),
            ModelResponse(content="", tool_calls=[repeat_call]),
            ModelResponse(content="OK I'll stop repeating"),
        ],
    )
    agent = _build_agent(model, registry, policy_allow_all)
    answer = agent.run("Loop please")
    assert "stop" in answer.lower()
