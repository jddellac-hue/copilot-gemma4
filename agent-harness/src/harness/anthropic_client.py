"""Anthropic (Claude) model client.

Implements the same ``ModelClient`` protocol as ``OllamaClient`` so it can
be swapped in transparently. Converts the harness internal message format
(Ollama/OpenAI-style) to the Anthropic Messages API format and back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from harness.model import ModelCallError, ModelResponse, ToolCall

logger = logging.getLogger(__name__)


@dataclass
class AnthropicConfig:
    """Tunables exposed in profile YAML."""

    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.2
    max_tokens: int = 4096


class AnthropicClient:
    """Thin wrapper around the Anthropic Messages API.

    The ``ANTHROPIC_API_KEY`` env-var is read automatically by the SDK.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    # ------------------------------------------------------------------
    # Public interface (satisfies ModelClient protocol)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        system, api_messages = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            raw = self._client.messages.create(**kwargs)
        except Exception as exc:
            logger.exception("Anthropic API call failed")
            raise ModelCallError(str(exc)) from exc

        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Message format conversion (harness → Anthropic)
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert harness messages to Anthropic format.

        Returns (system_prompt, api_messages).
        """
        system = ""
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg["role"]

            if role == "system":
                system = msg.get("content", "")
                continue

            if role == "user":
                api_messages.append({"role": "user", "content": msg["content"]})
                continue

            if role == "assistant":
                content_blocks: list[dict[str, Any]] = []
                text = msg.get("content", "")
                if text:
                    content_blocks.append({"type": "text", "text": text})
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": fn["name"],
                        "input": fn.get("arguments", {}),
                    })
                api_messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                continue

            if role == "tool":
                # Anthropic expects tool results as user messages with
                # tool_result content blocks.  Group consecutive tool
                # results into a single user message.
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                }
                # Append to previous user message if it already holds
                # tool_result blocks, otherwise start a new one.
                if (
                    api_messages
                    and api_messages[-1]["role"] == "user"
                    and isinstance(api_messages[-1]["content"], list)
                    and api_messages[-1]["content"]
                    and api_messages[-1]["content"][0].get("type") == "tool_result"
                ):
                    api_messages[-1]["content"].append(block)
                else:
                    api_messages.append({
                        "role": "user",
                        "content": [block],
                    })
                continue

            logger.warning("Skipping message with unknown role: %s", role)

        return system, api_messages

    @staticmethod
    def _convert_tools(
        ollama_tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert Ollama/OpenAI tool schemas to Anthropic format."""
        anthropic_tools: list[dict[str, Any]] = []
        for t in ollama_tools:
            fn = t.get("function", t)
            anthropic_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object"}),
            })
        return anthropic_tools

    # ------------------------------------------------------------------
    # Response parsing (Anthropic → harness)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: Any) -> ModelResponse:
        """Convert an Anthropic response into a harness ModelResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in raw.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        return ModelResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            raw_message={"stop_reason": raw.stop_reason},
            input_tokens=raw.usage.input_tokens,
            output_tokens=raw.usage.output_tokens,
        )
