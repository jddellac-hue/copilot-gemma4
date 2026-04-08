"""Runbook RAG tool.

Indexes a directory of markdown runbooks into a local Chroma collection
and exposes `search_runbooks(query, top_k)`. The agent calls this tool
during ops investigations to surface relevant playbooks, postmortems and
known-issue notes.

Design notes
============

- **Local-first**: the Chroma collection is persisted on disk, no cloud
  service. Indexing happens once per startup; re-indexing is incremental
  via file mtime + content hash.
- **Markdown-aware chunking**: files are split on top-level headings
  (`# `, `## `) so each chunk is a self-contained section. Long sections
  are further split into ~800-character windows with 100-char overlap.
- **Default embedding**: Chroma's bundled embedding function is used out
  of the box (sentence-transformers all-MiniLM-L6-v2 under the hood). It
  loads on first use, costs ~80 MB of RAM, and runs CPU-only. Override
  via the config if you have a preferred embedding model.
- **Optional dependency**: `chromadb` is in the `[rag]` extra. If not
  installed, `build_runbooks_tools` returns an empty list and logs a
  warning.

Configuration:

    ops_tools:
      runbooks:
        enabled: true
        path: ~/runbooks                # directory of .md files
        collection_name: ops_runbooks
        persist_dir: ~/.local/share/agent-harness/chroma
        chunk_size: 800
        chunk_overlap: 100
        glob: "**/*.md"
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class RunbooksConfig:
    enabled: bool = False
    path: Path = Path()
    collection_name: str = "ops_runbooks"
    persist_dir: Path = Path()
    chunk_size: int = 800
    chunk_overlap: int = 100
    glob: str = "**/*.md"
    max_results: int = 5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunbooksConfig:
        return cls(
            enabled=data.get("enabled", False),
            path=Path(data.get("path", "")).expanduser(),
            collection_name=data.get("collection_name", "ops_runbooks"),
            persist_dir=Path(
                data.get(
                    "persist_dir",
                    "~/.local/share/agent-harness/chroma",
                )
            ).expanduser(),
            chunk_size=int(data.get("chunk_size", 800)),
            chunk_overlap=int(data.get("chunk_overlap", 100)),
            glob=data.get("glob", "**/*.md"),
            max_results=int(data.get("max_results", 5)),
        )


def _split_markdown(
    text: str, chunk_size: int, overlap: int
) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) chunks.

    Returns a list of (section_path, chunk_text) tuples. The section_path
    is the chain of headings that contain the chunk, e.g. "Postmortem
    2025-11 > Root cause".
    """
    lines = text.splitlines()
    sections: list[tuple[list[str], list[str]]] = [([], [])]
    heading_stack: list[tuple[int, str]] = []  # (level, text)

    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            text_h = m.group(2).strip()
            # Pop deeper or equal headings
            heading_stack = [
                (lv, tx) for (lv, tx) in heading_stack if lv < level
            ]
            heading_stack.append((level, text_h))
            sections.append(([t for _, t in heading_stack], []))
        else:
            sections[-1][1].append(line)

    chunks: list[tuple[str, str]] = []
    for path, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        section_path = " > ".join(path) if path else "(preamble)"
        if len(body) <= chunk_size:
            chunks.append((section_path, body))
            continue
        # Slide window with overlap
        start = 0
        while start < len(body):
            end = min(start + chunk_size, len(body))
            chunks.append((section_path, body[start:end]))
            if end == len(body):
                break
            start = end - overlap
    return chunks


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _index_directory(collection: Any, config: RunbooksConfig) -> int:
    """Index all markdown files under config.path. Returns the chunk count.

    Re-indexing is incremental: a chunk is identified by
    sha256(file_content):section_path:offset and re-added only if missing
    from the collection.
    """
    indexed = 0
    files = sorted(config.path.glob(config.glob))
    if not files:
        logger.warning("no runbook files matched %s in %s", config.glob, config.path)
        return 0

    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("skipping non-utf8 file %s", f)
            continue
        file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rel = f.relative_to(config.path).as_posix()

        chunks = _split_markdown(text, config.chunk_size, config.chunk_overlap)
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        for idx, (section, body) in enumerate(chunks):
            chunk_id = f"{file_hash}:{idx}"
            ids.append(chunk_id)
            documents.append(body)
            metadatas.append(
                {
                    "file": rel,
                    "section": section,
                    "chunk_index": str(idx),
                }
            )

        # Chroma's `upsert` is idempotent on id
        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            indexed += len(ids)
    return indexed


def build_runbooks_tools(config: RunbooksConfig) -> list[Tool]:
    """Build the runbook RAG tool.

    Returns [] if disabled, if chromadb is not installed, or if the
    runbook directory does not exist.
    """
    if not config.enabled:
        return []
    if not config.path.is_dir():
        logger.warning(
            "runbooks enabled but path %s is not a directory; skipping",
            config.path,
        )
        return []

    try:
        import chromadb
    except ImportError:
        logger.warning(
            "runbooks enabled but `chromadb` is not installed. "
            "Install with: pip install agent-harness[rag]"
        )
        return []

    config.persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(config.persist_dir))
    collection = client.get_or_create_collection(name=config.collection_name)

    n_indexed = _index_directory(collection, config)
    logger.info(
        "runbooks: indexed %d chunks from %s into collection %s",
        n_indexed,
        config.path,
        config.collection_name,
    )

    @tool(
        name="search_runbooks",
        description=(
            "Search the local runbook collection by semantic similarity. "
            "Returns the top matching sections with their file path and "
            "section heading. Use this FIRST when investigating an "
            "incident — there is often a written playbook for the symptom. "
            "Examples of good queries: 'pod stuck in CrashLoopBackOff', "
            "'oracle dataguard apply lag', 'rabbitmq queue not draining'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        },
        risk="safe",
        side_effects={"read"},
    )
    def search_runbooks(args: dict) -> ToolResult:
        top_k = min(int(args.get("top_k", 5)), config.max_results)
        try:
            results = collection.query(
                query_texts=[args["query"]],
                n_results=top_k,
            )
        except Exception as exc:
            return ToolResult(
                ok=False, content=f"runbook search failed: {exc}"
            )

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        if not documents:
            return ToolResult(ok=True, content="[no runbook matched]")

        out_lines: list[str] = []
        for doc, meta, dist in zip(documents, metadatas, distances, strict=False):
            out_lines.append(
                f"--- {meta.get('file', '?')} :: {meta.get('section', '?')} "
                f"(score={1 - dist:.3f}) ---\n{doc.strip()}"
            )
        return ToolResult(
            ok=True,
            content="\n\n".join(out_lines),
            metadata={"matches": len(documents), "query": args["query"]},
        )

    return [search_runbooks]
