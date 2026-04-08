"""Domain skills RAG tool.

Indexes a directory of domain skill documents into a local Chroma collection
and exposes `search_skills(query, domain?)`.  Each subdirectory under the
skills path is a **domain** (e.g. angular, oracle, quarkus).  The agent
calls this tool to retrieve detailed domain expertise on demand.

Design notes
============

- Reuses the same Chroma + markdown chunking approach as ``runbooks.py``.
- Each chunk carries a ``domain`` metadata field derived from the
  top-level subdirectory name, enabling filtered searches.
- Indexes ``SKILL.md`` plus any ``references/*.md`` and ``versions/*.md``
  inside each skill directory.
- Optional dependency: ``chromadb`` (``[rag]`` extra).  If not installed,
  ``build_skills_tools`` returns an empty list with a warning.

Directory layout expected::

    skills/
    ├── angular/
    │   ├── SKILL.md
    │   └── versions/angular-15.md
    ├── oracle/
    │   ├── SKILL.md
    │   └── references/...
    └── ...

Configuration::

    ops_tools:
      skills:
        enabled: true
        path: skills                    # relative to workspace
        collection_name: agent_skills
        persist_dir: ~/.local/share/agent-harness/chroma
        chunk_size: 800
        chunk_overlap: 100
        max_results: 5
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.tools.base import Tool, ToolResult, tool

logger = logging.getLogger(__name__)


@dataclass
class SkillsConfig:
    enabled: bool = False
    path: Path = Path()
    collection_name: str = "agent_skills"
    persist_dir: Path = Path()
    chunk_size: int = 800
    chunk_overlap: int = 100
    max_results: int = 5

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: Path | None = None) -> SkillsConfig:
        raw_path = Path(data.get("path", "")).expanduser()
        # Resolve relative paths against the provided base directory
        if base_dir and not raw_path.is_absolute():
            raw_path = base_dir / raw_path
        return cls(
            enabled=data.get("enabled", False),
            path=raw_path,
            collection_name=data.get("collection_name", "agent_skills"),
            persist_dir=Path(
                data.get(
                    "persist_dir",
                    "~/.local/share/agent-harness/chroma",
                )
            ).expanduser(),
            chunk_size=int(data.get("chunk_size", 800)),
            chunk_overlap=int(data.get("chunk_overlap", 100)),
            max_results=int(data.get("max_results", 5)),
        )


def _detect_domain(file_path: Path, skills_root: Path) -> str:
    """Extract the domain name from a file path relative to the skills root.

    ``skills/angular/SKILL.md`` -> ``angular``
    ``skills/oracle/references/dql.md`` -> ``oracle``
    """
    try:
        rel = file_path.relative_to(skills_root)
    except ValueError:
        return "unknown"
    parts = rel.parts
    return parts[0] if parts else "unknown"


def _index_skills(collection: Any, config: SkillsConfig) -> tuple[int, list[str]]:
    """Index all markdown files under config.path.

    Returns (chunk_count, list_of_domains).
    """
    # Reuse the markdown chunker from runbooks — it is pure logic
    from harness.tools.runbooks import _split_markdown

    indexed = 0
    domains: set[str] = set()
    files = sorted(config.path.rglob("*.md"))
    if not files:
        logger.warning("no skill files found under %s", config.path)
        return 0, []

    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("skipping non-utf8 file %s", f)
            continue

        domain = _detect_domain(f, config.path)
        domains.add(domain)
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
                    "domain": domain,
                    "chunk_index": str(idx),
                }
            )

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            indexed += len(ids)

    return indexed, sorted(domains)


def build_skills_tools(config: SkillsConfig) -> list[Tool]:
    """Build the domain skills RAG tool.

    Returns [] if disabled, if chromadb is not installed, or if the
    skills directory does not exist.
    """
    if not config.enabled:
        return []
    if not config.path.is_dir():
        logger.warning(
            "skills enabled but path %s is not a directory; skipping",
            config.path,
        )
        return []

    try:
        import chromadb
    except ImportError:
        logger.warning(
            "skills enabled but `chromadb` is not installed. "
            "Install with: pip install agent-harness[rag]"
        )
        return []

    config.persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(config.persist_dir))
    collection = client.get_or_create_collection(name=config.collection_name)

    n_indexed, domains = _index_skills(collection, config)
    logger.info(
        "skills: indexed %d chunks from %d domains (%s) into collection %s",
        n_indexed,
        len(domains),
        ", ".join(domains),
        config.collection_name,
    )

    domain_list = ", ".join(domains) if domains else "none"

    @tool(
        name="search_skills",
        description=(
            "Search domain expertise by semantic similarity. "
            "Returns detailed knowledge about technologies, patterns, "
            "and best practices. Available domains: " + domain_list + ". "
            "Use 'domain' to restrict results to a specific area. "
            "Examples: query='Kafka consumer acknowledgment strategy' domain='quarkus', "
            "query='DQL filter tags' domain='dynatrace', "
            "query='Flyway migration order'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "Optional: restrict search to a specific skill domain "
                        f"({domain_list})"
                    ),
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
    def search_skills(args: dict) -> ToolResult:
        top_k = min(int(args.get("top_k", 5)), config.max_results)
        where_filter: dict[str, str] | None = None
        domain = args.get("domain")
        if domain and isinstance(domain, str):
            where_filter = {"domain": domain}

        try:
            query_kwargs: dict[str, Any] = {
                "query_texts": [args["query"]],
                "n_results": top_k,
            }
            if where_filter is not None:
                query_kwargs["where"] = where_filter
            results = collection.query(**query_kwargs)
        except Exception as exc:
            return ToolResult(
                ok=False, content=f"skill search failed: {exc}"
            )

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        if not documents:
            return ToolResult(ok=True, content="[no skill matched]")

        out_lines: list[str] = []
        for doc, meta, dist in zip(documents, metadatas, distances, strict=False):
            header = (
                f"--- [{meta.get('domain', '?')}] "
                f"{meta.get('file', '?')} :: {meta.get('section', '?')} "
                f"(score={1 - dist:.3f}) ---"
            )
            out_lines.append(f"{header}\n{doc.strip()}")

        return ToolResult(
            ok=True,
            content="\n\n".join(out_lines),
            metadata={
                "matches": len(documents),
                "query": args["query"],
                "domain_filter": domain,
            },
        )

    return [search_skills]
