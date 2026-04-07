"""Filesystem tools, scoped to a workspace root.

All filesystem access goes through `_resolve()` which prevents escaping the
workspace via `..` or absolute paths.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from harness.tools.base import Tool, ToolResult, tool

# Default size limits — can be overridden by config
MAX_READ_BYTES = 256 * 1024  # 256 KiB
MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 200

# Filenames the agent must never read, even inside the workspace
DENY_FILENAMES = {
    ".env",
    "credentials",
    "id_rsa",
    "id_ed25519",
    ".netrc",
}


class WorkspaceError(RuntimeError):
    pass


def _resolve(workspace: Path, relpath: str) -> Path:
    """Resolve a path relative to the workspace, refusing escapes."""
    workspace = workspace.resolve()
    candidate = (workspace / relpath).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise WorkspaceError(
            f"path {relpath!r} escapes workspace {workspace}"
        ) from exc
    if candidate.name in DENY_FILENAMES:
        raise WorkspaceError(f"access to {candidate.name!r} is denied")
    return candidate


def build_filesystem_tools(workspace: Path) -> list[Tool]:
    """Build filesystem tools bound to a specific workspace root."""
    workspace = workspace.resolve()

    @tool(
        name="read_file",
        description=(
            "Read the contents of a file in the workspace. Paths are relative "
            "to the workspace root. Returns up to 256 KiB; for larger files, "
            "use the offset/limit parameters to paginate."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace"},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "default": MAX_READ_BYTES},
            },
            "required": ["path"],
        },
        risk="safe",
        side_effects={"read"},
    )
    def read_file(args: dict) -> ToolResult:
        path = _resolve(workspace, args["path"])
        if not path.is_file():
            return ToolResult(ok=False, content=f"not a file: {args['path']}")
        offset = int(args.get("offset", 0))
        limit = min(int(args.get("limit", MAX_READ_BYTES)), MAX_READ_BYTES)
        data = path.read_bytes()[offset : offset + limit]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                ok=False,
                content=f"file appears to be binary: {args['path']}",
            )
        return ToolResult(
            ok=True,
            content=text,
            metadata={"size_bytes": path.stat().st_size, "returned_bytes": len(data)},
        )

    @tool(
        name="list_dir",
        description=(
            "List the contents of a directory in the workspace. Returns up to "
            f"{MAX_LIST_ENTRIES} entries with type (file/dir) and size."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
            },
        },
        risk="safe",
        side_effects={"read"},
    )
    def list_dir(args: dict) -> ToolResult:
        path = _resolve(workspace, args.get("path", "."))
        if not path.is_dir():
            return ToolResult(ok=False, content=f"not a directory: {args.get('path')}")
        entries = []
        for entry in sorted(path.iterdir())[:MAX_LIST_ENTRIES]:
            kind = "dir" if entry.is_dir() else "file"
            size = entry.stat().st_size if entry.is_file() else 0
            entries.append(f"{kind}\t{size}\t{entry.name}")
        return ToolResult(ok=True, content="\n".join(entries))

    @tool(
        name="search_files",
        description=(
            "Find files in the workspace by glob pattern. Example patterns: "
            "'**/*.java', 'src/**/test_*.py'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
            },
            "required": ["pattern"],
        },
        risk="safe",
        side_effects={"read"},
    )
    def search_files(args: dict) -> ToolResult:
        pattern = args["pattern"]
        results: list[str] = []
        for root, dirs, files in os.walk(workspace):
            # Skip hidden / vendored directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for fn in files:
                full = Path(root) / fn
                rel = full.relative_to(workspace).as_posix()
                if fnmatch.fnmatch(rel, pattern):
                    results.append(rel)
                    if len(results) >= MAX_SEARCH_RESULTS:
                        break
            if len(results) >= MAX_SEARCH_RESULTS:
                break
        return ToolResult(ok=True, content="\n".join(results))

    @tool(
        name="write_file",
        description=(
            "Create or overwrite a file in the workspace. Use this to add new "
            "files. To modify an existing file, prefer `edit_file`."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        risk="moderate",
        side_effects={"write"},
    )
    def write_file(args: dict) -> ToolResult:
        path = _resolve(workspace, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        return ToolResult(
            ok=True,
            content=f"wrote {len(args['content'])} chars to {args['path']}",
        )

    @tool(
        name="edit_file",
        description=(
            "Edit an existing file by replacing a unique substring. The "
            "`old_str` must appear EXACTLY ONCE in the file; otherwise the "
            "edit is refused. Use this for surgical modifications."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
        risk="moderate",
        side_effects={"write"},
    )
    def edit_file(args: dict) -> ToolResult:
        path = _resolve(workspace, args["path"])
        if not path.is_file():
            return ToolResult(ok=False, content=f"not a file: {args['path']}")
        text = path.read_text(encoding="utf-8")
        count = text.count(args["old_str"])
        if count == 0:
            return ToolResult(ok=False, content="old_str not found in file")
        if count > 1:
            return ToolResult(
                ok=False,
                content=f"old_str matches {count} times — must be unique",
            )
        new_text = text.replace(args["old_str"], args["new_str"], 1)
        path.write_text(new_text, encoding="utf-8")
        return ToolResult(ok=True, content=f"edited {args['path']}")

    return [read_file, list_dir, search_files, write_file, edit_file]
