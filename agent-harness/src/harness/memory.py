"""Conversation memory with compaction.

Two-tier:
- Working memory: the live message list passed to the model.
- Long-term: persistent notes on disk (markdown), opt-in via tools.

Compaction is triggered when working memory exceeds a soft token budget.
Token counting is approximate (chars / 4); good enough for budgeting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough estimate: 1 token ≈ 4 characters of UTF-8."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total_chars += len(str(part.get("text", "")))
    return total_chars // 4


@dataclass
class Memory:
    """Manages the working memory of an agent session."""

    system_prompt: str
    soft_budget_tokens: int = 6000
    pinned_message_ids: set[int] = field(default_factory=set)
    _messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self._messages:
            self._messages = [{"role": "system", "content": self.system_prompt}]

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    def append(self, message: dict[str, Any], pinned: bool = False) -> None:
        self._messages.append(message)
        if pinned:
            self.pinned_message_ids.add(len(self._messages) - 1)

    def needs_compaction(self) -> bool:
        return estimate_tokens(self._messages) > self.soft_budget_tokens

    def compact(self, summarizer: callable) -> None:  # type: ignore[valid-type]
        """Replace older non-pinned messages with a summary.

        `summarizer` must accept a list of messages and return a string.
        The system message and pinned messages are preserved.
        """
        if len(self._messages) < 6:
            return
        keep_recent = 4
        head = [self._messages[0]]  # system
        keep_pinned = [
            m
            for i, m in enumerate(self._messages[1:-keep_recent], start=1)
            if i in self.pinned_message_ids
        ]
        to_summarize = [
            m
            for i, m in enumerate(self._messages[1:-keep_recent], start=1)
            if i not in self.pinned_message_ids
        ]
        if not to_summarize:
            return
        summary = summarizer(to_summarize)
        summary_msg = {
            "role": "system",
            "content": f"[Summary of earlier conversation]\n{summary}",
        }
        tail = self._messages[-keep_recent:]
        self._messages = head + keep_pinned + [summary_msg] + tail
        self.pinned_message_ids = set()
        logger.info(
            "compacted memory: kept %d messages, summarised %d",
            len(self._messages),
            len(to_summarize),
        )


class LongTermStore:
    """Append-only markdown notes for facts the agent should remember."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("# Agent long-term notes\n\n", encoding="utf-8")

    def append(self, note: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"- {note}\n")

    def read_all(self) -> str:
        return self.path.read_text(encoding="utf-8")
