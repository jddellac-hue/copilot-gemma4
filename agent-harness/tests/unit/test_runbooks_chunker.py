"""Unit tests for the runbooks markdown chunker.

Chroma itself is an optional dep and is not exercised here — we only test
the markdown splitting logic, which is pure Python.
"""

from __future__ import annotations

from harness.tools.runbooks import RunbooksConfig, _split_markdown


def test_split_simple_document_with_headings():
    md = """# Title

Intro text.

## Section A

Content of A.

## Section B

Content of B.
"""
    chunks = _split_markdown(md, chunk_size=800, overlap=100)
    sections = [s for s, _ in chunks]
    assert "Title" in sections
    assert "Title > Section A" in sections
    assert "Title > Section B" in sections


def test_split_handles_nested_headings():
    md = """# Top

## Sub

### Deep

stuff
"""
    chunks = _split_markdown(md, chunk_size=800, overlap=100)
    paths = [s for s, _ in chunks]
    assert any("Top > Sub > Deep" in p for p in paths)


def test_split_long_section_uses_window():
    body = "x" * 2000
    md = f"# T\n\n{body}\n"
    chunks = _split_markdown(md, chunk_size=500, overlap=50)
    bodies = [b for _, b in chunks]
    assert len(bodies) > 1
    # Each chunk respects the size cap
    assert all(len(b) <= 500 for b in bodies)
    # Overlap means consecutive chunks share characters
    if len(bodies) >= 2:
        assert bodies[0][-50:] == bodies[1][:50]


def test_split_drops_empty_sections():
    md = """# Title

## Empty

## Real

content
"""
    chunks = _split_markdown(md, chunk_size=800, overlap=100)
    sections = {s for s, _ in chunks}
    # Empty section is not included as a chunk on its own
    assert "Title > Empty" not in sections
    assert "Title > Real" in sections


def test_runbooks_config_defaults():
    cfg = RunbooksConfig.from_dict({})
    assert cfg.enabled is False
    assert cfg.chunk_size == 800
    assert cfg.glob == "**/*.md"


def test_runbooks_config_path_expansion():
    cfg = RunbooksConfig.from_dict({"path": "~/runbooks", "enabled": True})
    assert "~" not in str(cfg.path)
