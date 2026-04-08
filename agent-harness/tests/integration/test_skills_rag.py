"""Integration test for the skills RAG pipeline.

Builds a real Chroma collection from test skill files, then runs
search queries and verifies the results are relevant. Requires the
chromadb package (``[rag]`` extra).
"""

from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip(
    "chromadb", reason="chromadb not installed (pip install agent-harness[rag])"
)

from harness.tools.skills import SkillsConfig, build_skills_tools


@pytest.fixture()
def skills_dir(tmp_path: Path) -> Path:
    """Create a minimal but realistic skills directory."""
    # quarkus skill
    quarkus = tmp_path / "quarkus"
    quarkus.mkdir()
    (quarkus / "SKILL.md").write_text(
        "# Quarkus\n\n"
        "## Kafka\n\n"
        "The recommended acknowledgment strategy for Quarkus Kafka consumers is\n"
        "PRE_PROCESSING for at-most-once delivery. Use @Blocking for synchronous\n"
        "processing and dead-letter-queue as failure strategy.\n\n"
        "## Datasources\n\n"
        "Quarkus supports dual datasources: primary (read-only) and db-secondary\n"
        "(Flyway-managed, write).\n"
    )

    # kubernetes skill
    k8s = tmp_path / "kubernetes"
    k8s.mkdir()
    (k8s / "SKILL.md").write_text(
        "# Kubernetes\n\n"
        "## CrashLoopBackOff\n\n"
        "Pod in CrashLoopBackOff: check kubectl describe pod for Events and\n"
        "Last State. Use kubectl logs --previous for crashed container logs.\n"
        "Common causes: OOMKilled (exit 137), app error (exit 1), liveness\n"
        "probe too aggressive.\n\n"
        "## Probes\n\n"
        "livenessProbe checks if the container is alive. readinessProbe checks\n"
        "if it accepts traffic. startupProbe disables liveness/readiness during\n"
        "slow startups.\n"
    )

    # angular skill
    angular = tmp_path / "angular"
    angular.mkdir()
    (angular / "SKILL.md").write_text(
        "# Angular\n\n"
        "## Testing\n\n"
        "Use Jest for unit tests and Cypress for E2E. Angular 15 uses\n"
        "TypeScript 4.9 and Node 18.\n"
    )

    return tmp_path


@pytest.fixture()
def skills_tools(skills_dir: Path, tmp_path: Path):
    """Build the search_rag tool with a real Chroma collection."""
    persist_dir = tmp_path / "chroma_test"
    config = SkillsConfig(
        enabled=True,
        path=skills_dir,
        collection_name="test_skills",
        persist_dir=persist_dir,
        chunk_size=800,
        chunk_overlap=100,
        max_results=5,
    )
    tools = build_skills_tools(config)
    assert len(tools) == 1, "Expected exactly one tool (search_rag)"
    return tools[0]


def test_search_returns_relevant_domain(skills_tools):
    """A Kafka query should return quarkus domain chunks."""
    result = skills_tools.invoke({"query": "Kafka acknowledgment strategy"})
    assert result.ok
    assert "PRE_PROCESSING" in result.content
    assert "[quarkus]" in result.content


def test_search_with_domain_filter(skills_tools):
    """Filtering by domain restricts results to that domain only."""
    result = skills_tools.invoke({
        "query": "pod crash",
        "domain": "kubernetes",
    })
    assert result.ok
    assert "[kubernetes]" in result.content
    assert "CrashLoopBackOff" in result.content
    # Should NOT contain angular or quarkus content
    assert "[angular]" not in result.content
    assert "[quarkus]" not in result.content


def test_search_wrong_domain_returns_empty(skills_tools):
    """Querying a non-existent domain returns no matches."""
    result = skills_tools.invoke({
        "query": "anything",
        "domain": "nonexistent",
    })
    assert result.ok
    assert "no skill matched" in result.content


def test_search_kubernetes_probes(skills_tools):
    """A probes query should find the kubernetes skill."""
    result = skills_tools.invoke({"query": "liveness readiness probe"})
    assert result.ok
    assert "livenessProbe" in result.content or "liveness" in result.content


def test_search_angular_testing(skills_tools):
    """An Angular testing query should return angular domain."""
    result = skills_tools.invoke({
        "query": "Jest unit tests Angular",
        "domain": "angular",
    })
    assert result.ok
    assert "[angular]" in result.content
    assert "Jest" in result.content


def test_search_metadata_fields(skills_tools):
    """Result metadata should contain matches count and query."""
    result = skills_tools.invoke({"query": "Kafka consumer", "top_k": 3})
    assert result.ok
    assert result.metadata["matches"] <= 3
    assert result.metadata["query"] == "Kafka consumer"


def test_tool_schema_lists_domains(skills_tools):
    """The tool description should list available domains."""
    desc = skills_tools.description
    assert "angular" in desc
    assert "kubernetes" in desc
    assert "quarkus" in desc
