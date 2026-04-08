"""Domain skills RAG tool.

Indexes a directory of domain skill documents into a local Chroma collection
and exposes ``search_rag(query, domain?)``.  Each subdirectory under the
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
- Lazy initialization: Chroma is loaded on first ``search_rag`` call,
  not during tool construction.  This keeps MCP server startup fast.

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

# Stamp file name shared with bash scripts (harness-run.sh, skills:reindex).
_STAMP_NAME = ".skills_indexed_at"


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


def _discover_domains(skills_path: Path) -> list[str]:
    """Return sorted list of domain names from the skills directory."""
    if not skills_path.is_dir():
        return []
    return sorted(
        d.name
        for d in skills_path.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )


def _needs_reindex(config: SkillsConfig) -> bool:
    """Check whether skills files have changed since the last index.

    Uses the shared stamp file ``.skills_indexed_at`` (same as the bash
    scripts) so that ``mise run skills:reindex`` and ``mise run chat``
    share the same freshness signal.
    """
    stamp = config.persist_dir / _STAMP_NAME
    if not stamp.exists():
        return True
    stamp_mtime = stamp.stat().st_mtime
    return any(f.is_file() and f.stat().st_mtime > stamp_mtime for f in config.path.rglob("*.md"))


def _touch_stamp(config: SkillsConfig) -> None:
    """Touch the stamp file to record the indexing time."""
    stamp = config.persist_dir / _STAMP_NAME
    stamp.touch()


def _index_skills(collection: Any, config: SkillsConfig) -> tuple[int, list[str]]:
    """Index all markdown files under config.path.

    Returns (chunk_count, list_of_domains).
    Skips re-indexing when the stamp file is newer than all skill files.
    """
    domains = _discover_domains(config.path)
    if not domains:
        logger.warning("no skill files found under %s", config.path)
        return 0, domains

    if not _needs_reindex(config):
        n_existing = collection.count()
        logger.info("skills index up-to-date (%d chunks), skipping reindex", n_existing)
        return n_existing, domains

    # Reuse the markdown chunker from runbooks — it is pure logic
    from harness.tools.runbooks import _split_markdown

    indexed = 0
    files = sorted(config.path.rglob("*.md"))

    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("skipping non-utf8 file %s", f)
            continue

        domain = _detect_domain(f, config.path)
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

    _touch_stamp(config)
    return indexed, domains


def build_skills_tools(config: SkillsConfig) -> list[Tool]:
    """Build the domain skills RAG tool.

    Returns [] if disabled, if the skills directory does not exist, or if
    no domains are found.  Chroma is loaded lazily on first
    ``search_rag`` call so that MCP server startup is not blocked.
    """
    if not config.enabled:
        return []
    if not config.path.is_dir():
        logger.warning(
            "skills enabled but path %s is not a directory; skipping",
            config.path,
        )
        return []

    # Discover domains from the filesystem (no chromadb needed)
    domains = _discover_domains(config.path)
    if not domains:
        logger.warning("no skill domains found under %s", config.path)
        return []

    domain_list = ", ".join(domains)

    # Lazy state — Chroma client + collection are created on first call
    _lazy: dict[str, Any] = {}

    def _ensure_collection() -> Any:
        """Import chromadb, open the collection, and index if needed.

        Called once on first search_rag invocation.  Subsequent calls
        return the cached collection.
        """
        if "collection" in _lazy:
            return _lazy["collection"]

        try:
            import chromadb
        except ImportError:
            logger.warning(
                "skills enabled but `chromadb` is not installed. "
                "Install with: pip install agent-harness[rag]"
            )
            _lazy["collection"] = None
            return None

        config.persist_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(config.persist_dir))
        collection = client.get_or_create_collection(name=config.collection_name)

        n_indexed, indexed_domains = _index_skills(collection, config)
        logger.info(
            "skills: %d chunks from %d domains (%s) in collection %s",
            n_indexed,
            len(indexed_domains),
            ", ".join(indexed_domains),
            config.collection_name,
        )
        _lazy["collection"] = collection
        return collection

    # Domain aliases — common abbreviations or partial names that should
    # match a known domain even when the exact directory name is not used.
    _domain_aliases: dict[str, str] = {
        "rabbit": "rabbitmq",
        "rmq": "rabbitmq",
        "amqp": "rabbitmq",
        "k8s": "kubernetes",
        "kube": "kubernetes",
        "helm": "kubernetes",
        "cf": "tanzu",
        "cloudfoundry": "tanzu",
        "cloud foundry": "tanzu",
        "tas": "tanzu",
        "bosh": "tanzu",
        "dt": "dynatrace",
        "dql": "dynatrace",
        "grail": "dynatrace",
        "sonar": "java",
        "jacoco": "java",
        "junit": "java",
        "maven": "java",
        "flyway": "oracle",
        "goldengate": "oracle",
        "n4ds": "dsn",
        "playwright": "test",
        "behave": "test",
        "cypress": "angular",
        "jest": "angular",
        "cookiecutter": "cutter",
        "streamlit": "cutter",
        "actuator": "spring",
        "kafka": "quarkus",
        "slo": "sre",
        "sli": "sre",
    }

    def _detect_domains_in_query(query: str) -> list[str]:
        """Detect domain names and aliases mentioned in the query text."""
        query_lower = query.lower()
        matched: set[str] = set()
        # Direct domain name match
        for d in domains:
            if d in query_lower:
                matched.add(d)
        # Alias match
        for alias, target in _domain_aliases.items():
            if alias in query_lower and target in domains:
                matched.add(target)
        return sorted(matched)

    def _query_collection(
        coll: Any, query: str, top_k: int, domain: str | None = None,
    ) -> list[tuple[str, dict[str, str], float]]:
        """Run a single Chroma query; returns list of (doc, meta, dist)."""
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": top_k}
        if domain:
            kwargs["where"] = {"domain": domain}
        results = coll.query(**kwargs)
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]
        return list(zip(docs, metas, dists, strict=False))

    @tool(
        name="search_rag",
        description=(
            "Search domain expertise by semantic similarity. "
            "Returns detailed knowledge about technologies, patterns, "
            "and best practices. Available domains: " + domain_list + ". "
            "When no domain is specified, domains mentioned in the query "
            "are auto-detected (including aliases like rabbit→rabbitmq, "
            "k8s→kubernetes, tas→tanzu). "
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
                        f"({domain_list}). Leave empty for auto-detection."
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
    def search_rag(args: dict[str, Any]) -> ToolResult:
        collection = _ensure_collection()
        if collection is None:
            return ToolResult(
                ok=False,
                content="chromadb not installed — run: pip install agent-harness[rag]",
            )

        query = args["query"]
        top_k = min(int(args.get("top_k", 5)), config.max_results)
        explicit_domain = args.get("domain")

        hits: list[tuple[str, dict[str, str], float]] = []
        try:
            if explicit_domain and isinstance(explicit_domain, str):
                # Explicit domain — single search, honour the caller
                hits = _query_collection(collection, query, top_k, explicit_domain)
            else:
                # Auto-detect: two-pass strategy
                # Pass 1 — targeted search per detected domain
                detected = _detect_domains_in_query(query)
                seen_ids: set[str] = set()
                per_domain = max(2, top_k // max(len(detected), 1))
                for d in detected:
                    for doc, meta, dist in _query_collection(collection, query, per_domain, d):
                        chunk_id = f"{meta.get('file')}:{meta.get('chunk_index')}"
                        if chunk_id not in seen_ids:
                            seen_ids.add(chunk_id)
                            hits.append((doc, meta, dist))

                # Pass 2 — general search to fill remaining slots
                remaining = top_k - len(hits)
                if remaining > 0:
                    for doc, meta, dist in _query_collection(
                        collection, query, remaining + 2
                    ):
                        chunk_id = f"{meta.get('file')}:{meta.get('chunk_index')}"
                        if chunk_id not in seen_ids and len(hits) < top_k:
                            seen_ids.add(chunk_id)
                            hits.append((doc, meta, dist))

        except Exception as exc:
            return ToolResult(
                ok=False, content=f"skill search failed: {exc}"
            )

        if not hits:
            return ToolResult(ok=True, content="[no skill matched]")

        out_lines: list[str] = []
        matched_domains: set[str] = set()
        for doc, meta, dist in hits:
            d = meta.get("domain", "?")
            matched_domains.add(d)
            header = (
                f"--- [{d}] "
                f"{meta.get('file', '?')} :: {meta.get('section', '?')} "
                f"(score={1 - dist:.3f}) ---"
            )
            out_lines.append(f"{header}\n{doc.strip()}")

        return ToolResult(
            ok=True,
            content="\n\n".join(out_lines),
            metadata={
                "matches": len(hits),
                "query": query,
                "domains": sorted(matched_domains),
                "domain_filter": explicit_domain,
            },
        )

    return [search_rag]
