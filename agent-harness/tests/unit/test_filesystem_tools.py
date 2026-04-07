"""Unit tests for the filesystem tools, focused on workspace escape prevention."""

from __future__ import annotations

from pathlib import Path

from harness.tools.filesystem import build_filesystem_tools


def test_read_file_inside_workspace(tmp_path: Path):
    (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["read_file"].invoke({"path": "hello.txt"})
    assert result.ok
    assert result.content == "world"


def test_read_file_escape_refused(tmp_path: Path):
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["read_file"].invoke({"path": "../../../etc/passwd"})
    assert not result.ok


def test_read_file_denied_filename(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET=hunter2", encoding="utf-8")
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["read_file"].invoke({"path": ".env"})
    assert not result.ok


def test_write_then_read_roundtrip(tmp_path: Path):
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    write_res = tools["write_file"].invoke(
        {"path": "out/data.txt", "content": "abc"}
    )
    assert write_res.ok
    read_res = tools["read_file"].invoke({"path": "out/data.txt"})
    assert read_res.ok and read_res.content == "abc"


def test_edit_file_unique_match(tmp_path: Path):
    (tmp_path / "x.py").write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["edit_file"].invoke(
        {"path": "x.py", "old_str": "VALUE = 1", "new_str": "VALUE = 99"}
    )
    assert result.ok
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == "VALUE = 99\nOTHER = 2\n"


def test_edit_file_ambiguous_match(tmp_path: Path):
    (tmp_path / "x.py").write_text("a = 1\nb = 1\n", encoding="utf-8")
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["edit_file"].invoke(
        {"path": "x.py", "old_str": "= 1", "new_str": "= 2"}
    )
    assert not result.ok
    assert "unique" in result.content


def test_search_files_glob(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").touch()
    (tmp_path / "src" / "b.py").touch()
    (tmp_path / "src" / "c.txt").touch()
    tools = {t.name: t for t in build_filesystem_tools(tmp_path)}
    result = tools["search_files"].invoke({"pattern": "src/*.py"})
    assert result.ok
    lines = [line for line in result.content.splitlines() if line]
    assert sorted(lines) == ["src/a.py", "src/b.py"]
