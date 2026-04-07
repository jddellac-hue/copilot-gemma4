"""Tool registry: holds all tools available to the agent."""

from __future__ import annotations

from typing import Any

from harness.tools.base import Tool, ToolResult


class ToolRegistry:
    """Central catalogue of tools.

    Tools are looked up by name; the registry can produce schemas for the
    model and dispatch invocations.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def ollama_schemas(self) -> list[dict[str, Any]]:
        """Schemas in the format expected by the Ollama chat API."""
        return [t.to_ollama_schema() for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                content=f"unknown tool: {name}. available: {self.names()}",
            )
        return tool.invoke(arguments)
