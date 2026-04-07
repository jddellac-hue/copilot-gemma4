"""Tool primitives: dataclass, decorator, result type."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from jsonschema import ValidationError, validate

RiskLevel = Literal["safe", "moderate", "dangerous"]
SideEffect = Literal["read", "write", "network", "exec"]


@dataclass
class ToolResult:
    """Result of a tool invocation, ready to be serialised back to the model."""

    ok: bool
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message_content(self, max_chars: int = 8000) -> str:
        """Render for re-injection into the conversation, truncating if needed."""
        body = self.content
        if len(body) > max_chars:
            body = (
                body[:max_chars]
                + f"\n\n[... truncated, {len(self.content) - max_chars} chars elided ...]"
            )
        if self.ok:
            return body
        return f"[ERROR] {body}"


@dataclass
class Tool:
    """A tool exposed to the model.

    Tools are first-class objects with a declared risk level and a set of
    side effects, so the permission system can reason about them uniformly.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[[dict[str, Any]], ToolResult]
    risk: RiskLevel = "safe"
    side_effects: set[SideEffect] = field(default_factory=set)

    def to_ollama_schema(self) -> dict[str, Any]:
        """Convert to the schema format expected by the Ollama tools API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_mcp_schema(self) -> dict[str, Any]:
        """Convert to MCP tool schema (for re-exposing the harness as MCP)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Raise jsonschema.ValidationError if arguments do not match."""
        validate(instance=arguments, schema=self.parameters)

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate then dispatch to the handler. Errors are wrapped."""
        try:
            self.validate_arguments(arguments)
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                content=f"invalid arguments for tool {self.name}: {exc.message}",
            )
        try:
            return self.handler(arguments)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                content=f"tool {self.name} raised an exception: {exc}",
            )


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    risk: RiskLevel = "safe",
    side_effects: set[SideEffect] | None = None,
) -> Callable[[Callable[[dict[str, Any]], ToolResult]], Tool]:
    """Decorator that turns a function into a `Tool`.

    Example:
        @tool(
            name="echo",
            description="Echo back the input string.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        def echo(args):
            return ToolResult(ok=True, content=args["text"])
    """

    def decorator(fn: Callable[[dict[str, Any]], ToolResult]) -> Tool:
        return Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            risk=risk,
            side_effects=side_effects or set(),
        )

    return decorator
