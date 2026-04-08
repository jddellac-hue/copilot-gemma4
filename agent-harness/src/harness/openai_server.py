"""OpenAI-compatible HTTP server wrapping the full agent loop.

Exposes ``/v1/chat/completions`` so that any client that speaks the
OpenAI protocol (JetBrains AI Assistant, Continue.dev, Open WebUI, …)
can use the harness as a drop-in LLM backend. Each request triggers a
full agentic session: the local model reasons, calls tools, and returns
the final answer.

This is NOT a raw model proxy — it is the full skeleton + brain.

Usage:
    harness openai-serve --profile config/profiles/gemma4-coding.yaml
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)


def create_app(profile: dict[str, Any], workspace: Path) -> Starlette:
    """Build a Starlette app that serves /v1/chat/completions."""

    from harness.cli import _build_agent

    def _extract_user_message(body: dict[str, Any]) -> str:
        """Extract the last user message from the OpenAI-format request."""
        messages = body.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Handle content blocks format
                    parts = [
                        b.get("text", "")
                        for b in content
                        if b.get("type") == "text"
                    ]
                    return "\n".join(parts)
                return str(content)
        return ""

    async def chat_completions(request: Request) -> JSONResponse:
        body = await request.json()
        user_message = _extract_user_message(body)

        if not user_message:
            return JSONResponse(
                {"error": {"message": "No user message found", "type": "invalid_request_error"}},
                status_code=400,
            )

        model_name = profile.get("model", {}).get("name", "local-agent")

        # Build a fresh agent for each request
        agent = _build_agent(profile, workspace)

        try:
            answer = agent.run(user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent run failed")
            answer = f"[Agent error] {exc}"

        # Format as OpenAI chat completion response
        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

        return JSONResponse(response)

    async def list_models(request: Request) -> JSONResponse:
        model_name = profile.get("model", {}).get("name", "local-agent")
        return JSONResponse({
            "object": "list",
            "data": [
                {
                    "id": model_name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "agent-harness",
                }
            ],
        })

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat_completions, methods=["POST"]),
            Route("/v1/models", list_models, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
        ],
    )


def run_server(
    profile: dict[str, Any],
    workspace: Path,
    host: str = "127.0.0.1",
    port: int = 11500,
) -> None:
    """Start the OpenAI-compatible server. Blocks until interrupted."""
    import uvicorn

    app = create_app(profile, workspace)
    model_name = profile.get("model", {}).get("name", "?")
    logger.info(
        "Starting OpenAI-compatible server on %s:%d (model: %s)",
        host, port, model_name,
    )
    print(f"\n=== Agent Harness — OpenAI-compatible server ===")
    print(f"  Endpoint : http://{host}:{port}/v1/chat/completions")
    print(f"  Model    : {model_name}")
    print(f"  Workspace: {workspace}")
    print(f"\n  Pour IntelliJ AI Assistant :")
    print(f"    URL : http://{host}:{port}/v1")
    print(f"    Clé : any-key-works")
    print(f"\n  Ctrl+C pour arrêter\n")

    uvicorn.run(app, host=host, port=port, log_level="warning")
