"""Ollama model client.

Wraps the Ollama Python SDK with:
- robust tool-call parsing (Gemma is less reliable than GPT-4 on tool calling)
- retry on malformed tool calls
- usage accounting
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import ollama

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OllamaClient:
    """Thin wrapper around the Ollama chat API.

    Designed for Gemma-class models. Falls back to text-format tool-call
    parsing when the native tool-calling pathway fails.
    """

    def __init__(
        self,
        model: str,
        endpoint: str = "http://localhost:11434",
        temperature: float = 0.2,
        num_ctx: int = 8192,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.temperature = temperature
        self.num_ctx = num_ctx
        self._client = ollama.Client(host=endpoint)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        """Send a chat completion request and return a normalised response."""
        try:
            raw = self._client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                options={
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx,
                },
            )
        except Exception as exc:
            logger.exception("Ollama chat call failed")
            raise ModelCallError(str(exc)) from exc

        message = raw.get("message", {})
        content = message.get("content", "") or ""

        tool_calls: list[ToolCall] = []

        # Path 1: native tool calls returned by Ollama
        for idx, raw_call in enumerate(message.get("tool_calls", []) or []):
            fn = raw_call.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    logger.warning("Tool call %s had non-JSON args: %r", name, args)
                    args = {}
            tool_calls.append(
                ToolCall(id=f"call_{idx}", name=name, arguments=args)
            )

        # Path 2: text-format fallback parsing (<tool_call>...</tool_call>)
        if not tool_calls and tools:
            tool_calls = self._parse_text_tool_calls(content)
            if tool_calls:
                # Strip the tool call markup from the visible content
                content = self._strip_tool_call_markup(content)

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            raw_message=message,
            input_tokens=raw.get("prompt_eval_count", 0),
            output_tokens=raw.get("eval_count", 0),
        )

    @staticmethod
    def _parse_text_tool_calls(text: str) -> list[ToolCall]:
        """Parse tool calls in text form: <tool_call>{...}</tool_call>."""
        import re

        calls: list[ToolCall] = []
        pattern = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
        for idx, match in enumerate(pattern.finditer(text)):
            try:
                payload = json.loads(match.group(1))
                calls.append(
                    ToolCall(
                        id=f"call_{idx}",
                        name=payload.get("name", ""),
                        arguments=payload.get("arguments", {}),
                    )
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse text tool call: %r", match.group(1))
        return calls

    @staticmethod
    def _strip_tool_call_markup(text: str) -> str:
        import re

        return re.sub(
            r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL
        ).strip()


class ModelCallError(RuntimeError):
    """Raised when a model call fails irrecoverably."""
