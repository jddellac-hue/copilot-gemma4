"""Unit tests for the skills RAG tool.

Mirrors the test pattern of test_runbooks_chunker.py: we test the pure
logic (domain detection, config parsing, indexing) without requiring
chromadb at import time.
"""

from __future__ import annotations

from pathlib import Path

from harness.tools.skills import (
    SkillsConfig,
    _detect_domain,
)

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_skills_config_defaults():
    cfg = SkillsConfig.from_dict({})
    assert cfg.enabled is False
    assert cfg.collection_name == "agent_skills"
    assert cfg.chunk_size == 800
    assert cfg.max_results == 5


def test_skills_config_path_expansion():
    cfg = SkillsConfig.from_dict({"path": "~/skills", "enabled": True})
    assert "~" not in str(cfg.path)
    assert cfg.enabled is True


def test_skills_config_custom_values():
    cfg = SkillsConfig.from_dict({
        "enabled": True,
        "path": "/tmp/skills",
        "collection_name": "custom_skills",
        "chunk_size": 400,
        "chunk_overlap": 50,
        "max_results": 10,
    })
    assert cfg.collection_name == "custom_skills"
    assert cfg.chunk_size == 400
    assert cfg.chunk_overlap == 50
    assert cfg.max_results == 10


# ---------------------------------------------------------------------------
# Domain detection tests
# ---------------------------------------------------------------------------

def test_detect_domain_from_skill_md():
    root = Path("/skills")
    assert _detect_domain(Path("/skills/angular/SKILL.md"), root) == "angular"


def test_detect_domain_from_nested_file():
    root = Path("/skills")
    assert _detect_domain(
        Path("/skills/oracle/references/dql.md"), root
    ) == "oracle"


def test_detect_domain_from_versions_file():
    root = Path("/skills")
    assert _detect_domain(
        Path("/skills/quarkus/versions/quarkus-3.x.md"), root
    ) == "quarkus"


def test_detect_domain_unknown_for_unrelated_path():
    root = Path("/skills")
    assert _detect_domain(Path("/other/file.md"), root) == "unknown"


# ---------------------------------------------------------------------------
# Indexing tests (with real files on disk, no chromadb)
# ---------------------------------------------------------------------------

def test_index_skills_populates_collection(tmp_path: Path):
    """Create a minimal skills directory and verify indexing."""
    # Setup: two skill directories with SKILL.md
    angular = tmp_path / "angular"
    angular.mkdir()
    (angular / "SKILL.md").write_text(
        "# Angular\n\nAngular 15 SPA frontend.\n\n"
        "## Testing\n\nUse Jest for unit tests.\n"
    )

    oracle = tmp_path / "oracle"
    oracle.mkdir()
    (oracle / "SKILL.md").write_text(
        "# Oracle\n\nOracle 19c administration.\n\n"
        "## CDB/PDB\n\nContainer database architecture.\n"
    )

    # A mock collection that records upsert calls
    upserts: list[dict] = []

    class FakeCollection:
        def upsert(self, ids, documents, metadatas):
            upserts.append({
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            })

    from harness.tools.skills import _index_skills

    config = SkillsConfig(
        enabled=True,
        path=tmp_path,
        chunk_size=800,
        chunk_overlap=100,
    )

    n_indexed, domains = _index_skills(FakeCollection(), config)

    assert n_indexed > 0
    assert "angular" in domains
    assert "oracle" in domains

    # Verify domain metadata is set correctly
    all_metadatas = [m for u in upserts for m in u["metadatas"]]
    angular_domains = {m["domain"] for m in all_metadatas if "angular" in m["file"]}
    oracle_domains = {m["domain"] for m in all_metadatas if "oracle" in m["file"]}
    assert angular_domains == {"angular"}
    assert oracle_domains == {"oracle"}


def test_index_skills_handles_nested_references(tmp_path: Path):
    """Skills with references/ subdirectory are indexed under the right domain."""
    dynatrace = tmp_path / "dynatrace"
    dynatrace.mkdir()
    (dynatrace / "SKILL.md").write_text("# Dynatrace\n\nDQL basics.\n")

    refs = dynatrace / "references"
    refs.mkdir()
    (refs / "dql-reference.md").write_text("# DQL Reference\n\nfetch logs.\n")

    upserts: list[dict] = []

    class FakeCollection:
        def upsert(self, ids, documents, metadatas):
            upserts.append({"metadatas": metadatas})

    from harness.tools.skills import _index_skills

    config = SkillsConfig(enabled=True, path=tmp_path, chunk_size=800, chunk_overlap=100)
    _n_indexed, domains = _index_skills(FakeCollection(), config)

    assert "dynatrace" in domains
    all_metadatas = [m for u in upserts for m in u["metadatas"]]
    # Both SKILL.md and references/dql-reference.md should be domain=dynatrace
    assert all(m["domain"] == "dynatrace" for m in all_metadatas)


def test_index_skills_empty_directory(tmp_path: Path):
    """Empty skills directory returns 0 chunks."""
    from harness.tools.skills import _index_skills

    class FakeCollection:
        def upsert(self, ids, documents, metadatas):
            pass

    config = SkillsConfig(enabled=True, path=tmp_path, chunk_size=800, chunk_overlap=100)
    n_indexed, domains = _index_skills(FakeCollection(), config)
    assert n_indexed == 0
    assert domains == []


def test_build_skills_tools_disabled():
    """Disabled config returns empty tool list."""
    from harness.tools.skills import build_skills_tools

    config = SkillsConfig(enabled=False)
    assert build_skills_tools(config) == []


def test_build_skills_tools_missing_directory(tmp_path: Path):
    """Non-existent path returns empty tool list."""
    from harness.tools.skills import build_skills_tools

    config = SkillsConfig(enabled=True, path=tmp_path / "nonexistent")
    assert build_skills_tools(config) == []
