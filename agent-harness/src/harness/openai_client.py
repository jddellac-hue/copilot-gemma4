"""OpenAI-compatible model client.

Works with any provider exposing an OpenAI-compatible chat/completions
endpoint: GitHub Copilot (Models API), OpenAI, Azure OpenAI, Groq,
Together, etc.

Implements the ``ModelClient`` protocol so it can be swapped in
transparently alongside OllamaClient and AnthropicClient.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

from harness.model import ModelCallError, ModelResponse, ToolCall

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Thin wrapper around the OpenAI Python SDK.

    The ``api_key`` is read from the environment variable named by
    ``api_key_env`` (default ``OPENAI_API_KEY``).  The ``base_url``
    controls which provider is hit.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise ModelCallError(
                f"environment variable {api_key_env} is not set"
            )

        self._client = OpenAI(base_url=base_url, api_key=api_key)

    # ------------------------------------------------------------------
    # Public interface (satisfies ModelClient protocol)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        api_messages = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools  # already in OpenAI format

        try:
            raw = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.exception("OpenAI-compatible API call failed")
            raise ModelCallError(str(exc)) from exc

        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Message format conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert harness internal messages to OpenAI format.

        The harness format is already very close to OpenAI — the main
        difference is that tool results use ``tool_call_id`` where OpenAI
        expects it at the top level of the message dict.
        """
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg["role"]

            if role == "system":
                api_messages.append({
                    "role": "system",
                    "content": msg["content"],
                })
            elif role == "user":
                api_messages.append({
                    "role": "user",
                    "content": msg["content"],
                })
            elif role == "assistant":
                out: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.get("content", "") or None,
                }
                if msg.get("tool_calls"):
                    out["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": (
                                    tc["function"]["arguments"]
                                    if isinstance(tc["function"]["arguments"], str)
                                    else json.dumps(
                                        tc["function"]["arguments"]
                                    )
                                ),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                api_messages.append(out)
            elif role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                })
            else:
                logger.warning("Skipping message with unknown role: %s", role)

        return api_messages

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: Any) -> ModelResponse:
        choice = raw.choices[0]
        message = choice.message
        content = message.content or ""

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        usage = raw.usage
        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            raw_message={"finish_reason": choice.finish_reason},
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
