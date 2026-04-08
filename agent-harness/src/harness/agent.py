"""Agent loop — ReAct-style orchestration around an Ollama model."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from harness.memory import Memory
from harness.model import ModelClient, ToolCall
from harness.observability import Observability
from harness.permissions import PermissionPolicy
from harness.tools import ToolRegistry

logger = logging.getLogger(__name__)

ConfirmCallback = Callable[[ToolCall], bool]


@dataclass
class AgentConfig:
    max_steps: int = 25
    token_budget: int = 50_000
    wall_clock_timeout_s: int = 600
    repetition_threshold: int = 3


class AgentError(RuntimeError):
    pass


class Agent:
    """Agent loop bundling model, tools, permissions, memory, observability."""

    def __init__(
        self,
        model: ModelClient,
        tools: ToolRegistry,
        permissions: PermissionPolicy,
        memory: Memory,
        observability: Observability,
        config: AgentConfig | None = None,
        confirm_callback: ConfirmCallback | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.permissions = permissions
        self.memory = memory
        self.obs = observability
        self.config = config or AgentConfig()
        self.confirm = confirm_callback or (lambda call: True)
        self._tokens_used = 0
        self._call_history: list[tuple[str, str]] = []

    def run(self, user_request: str) -> str:
        """Run the agent loop until completion or budget exhaustion."""
        session_id = str(uuid.uuid4())
        self.memory.append({"role": "user", "content": user_request})

        with self.obs.session(session_id):
            for step in range(self.config.max_steps):
                with self.obs.step(step):
                    if self.memory.needs_compaction():
                        self._compact_memory()

                    response = self._call_model()

                    if not response.has_tool_calls:
                        self.memory.append(
                            {"role": "assistant", "content": response.content}
                        )
                        return response.content

                    self.memory.append(
                        {
                            "role": "assistant",
                            "content": response.content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.name,
                                        "arguments": tc.arguments,
                                    },
                                }
                                for tc in response.tool_calls
                            ],
                        }
                    )

                    for call in response.tool_calls:
                        self._handle_tool_call(call)

                    if self._tokens_used > self.config.token_budget:
                        raise AgentError(
                            f"token budget exceeded: {self._tokens_used}"
                        )

        raise AgentError(f"max_steps reached: {self.config.max_steps}")

    def _call_model(self) -> Any:  # type: ignore[name-defined]
        with self.obs.model_call(self.model.model) as span:
            response = self.model.chat(
                messages=self.memory.messages,
                tools=self.tools.ollama_schemas(),
            )
            span.set_attribute("tokens.input", response.input_tokens)
            span.set_attribute("tokens.output", response.output_tokens)
            self._tokens_used += response.input_tokens + response.output_tokens
            self.obs.record_tokens(
                self.model.model, response.input_tokens, response.output_tokens
            )
            return response

    def _handle_tool_call(self, call: ToolCall) -> None:
        # Repetition detection
        signature = (call.name, str(sorted(call.arguments.items())))
        self._call_history.append(signature)
        if (
            self._call_history.count(signature)
            > self.config.repetition_threshold
        ):
            self._inject_tool_result(
                call,
                ok=False,
                content=(
                    "you have called this tool with the same arguments "
                    f"{self.config.repetition_threshold}+ times — try a "
                    "different approach or stop"
                ),
            )
            return

        decision = self.permissions.check(call.name, call.arguments)
        tool = self.tools.get(call.name)
        risk = tool.risk if tool else "unknown"

        with self.obs.tool_call(call.name, risk) as span:
            span.set_attribute("permission.decision", decision)

            if decision == "deny":
                self.obs.record_denied(call.name)
                self._inject_tool_result(
                    call, ok=False, content="permission denied by policy"
                )
                return

            if decision == "ask" and not self.confirm(call):
                self._inject_tool_result(
                    call, ok=False, content="user refused execution"
                )
                return

            result = self.tools.dispatch(call.name, call.arguments)
            span.set_attribute("tool.ok", result.ok)
            self._inject_tool_result(
                call, ok=result.ok, content=result.to_message_content()
            )

    def _inject_tool_result(
        self, call: ToolCall, ok: bool, content: str
    ) -> None:
        self.memory.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": content if ok else f"[ERROR] {content}",
            }
        )

    def _compact_memory(self) -> None:
        def summarize(messages: list[dict]) -> str:
            text = "\n".join(
                f"{m.get('role')}: {str(m.get('content', ''))[:200]}"
                for m in messages
            )
            response = self.model.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following conversation excerpt in "
                            "5 bullet points, preserving any decisions, file "
                            "paths, error messages and pending tasks."
                        ),
                    },
                    {"role": "user", "content": text},
                ]
            )
            return response.content

        self.memory.compact(summarize)
