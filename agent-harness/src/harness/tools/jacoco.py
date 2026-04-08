"""JaCoCo coverage report tool.

One read-only tool that parses a JaCoCo XML report and returns structured
coverage data:

- `jacoco_coverage`  — parse jacoco.xml, return coverage by class + top gaps

This tool operates on local files only (no network). It reads the XML
report produced by `mvn verify -Pjacoco` and returns a compact summary
the model can act on immediately.

No configuration needed — the tool takes the report path as an argument.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from harness.tools.base import Tool, ToolResult, tool


def build_jacoco_tool(workspace: Path) -> Tool:
    """Build the JaCoCo coverage tool scoped to a workspace."""

    @tool(
        name="jacoco_coverage",
        description=(
            "Parse a JaCoCo XML coverage report and return structured "
            "coverage data. Returns overall coverage percentages (instruction, "
            "branch, line, method) and the top classes with the most missed "
            "branches — so you know exactly where to write tests. "
            "The report is typically at <module>/target/site/jacoco/jacoco.xml "
            "after running `mvn verify -Pjacoco`."
        ),
        parameters={
            "type": "object",
            "properties": {
                "report_path": {
                    "type": "string",
                    "description": (
                        "Path to jacoco.xml relative to workspace "
                        "(e.g. 'target/site/jacoco/jacoco.xml' or "
                        "'my-module/target/site/jacoco/jacoco.xml')"
                    ),
                },
                "top_n": {
                    "type": "integer",
                    "description": (
                        "Number of worst-covered classes to show (default: 15)"
                    ),
                },
            },
            "required": ["report_path"],
        },
        risk="safe",
        side_effects={"read"},
    )
    def jacoco_coverage(args: dict[str, Any]) -> ToolResult:
        report_rel = args["report_path"]
        top_n = args.get("top_n", 15)

        # Resolve within workspace boundary
        report = (workspace / report_rel).resolve()
        if not str(report).startswith(str(workspace.resolve())):
            return ToolResult(ok=False, content="path traversal denied")
        if not report.exists():
            return ToolResult(
                ok=False,
                content=(
                    f"report not found: {report_rel}. "
                    "Run `mvn verify -Pjacoco -DskipITs` first."
                ),
            )

        try:
            tree = ET.parse(report)
        except ET.ParseError as exc:
            return ToolResult(ok=False, content=f"XML parse error: {exc}")

        root = tree.getroot()

        # Overall counters
        overall: dict[str, dict[str, int]] = {}
        for counter in root.findall("counter"):
            ctype = counter.get("type", "")
            missed = int(counter.get("missed", 0))
            covered = int(counter.get("covered", 0))
            overall[ctype] = {"missed": missed, "covered": covered}

        lines = ["=== JaCoCo Coverage Summary ===", ""]
        lines.append("metric\t\tcoverage\tmissed\tcovered")
        for ctype in ("INSTRUCTION", "BRANCH", "LINE", "METHOD", "CLASS"):
            if ctype in overall:
                m = overall[ctype]["missed"]
                c = overall[ctype]["covered"]
                total = m + c
                pct = (c / total * 100) if total else 0
                lines.append(f"{ctype}\t\t{pct:.1f}%\t\t{m}\t{c}")

        # Per-class branch gaps
        gaps: list[tuple[int, int, str]] = []
        for pkg in root.findall(".//package"):
            for cls in pkg.findall("class"):
                cls_name = cls.get("name", "?").replace("/", ".")
                for counter in cls.findall("counter[@type='BRANCH']"):
                    missed = int(counter.get("missed", 0))
                    covered = int(counter.get("covered", 0))
                    if missed > 0:
                        gaps.append((missed, covered, cls_name))

        if gaps:
            gaps.sort(reverse=True)
            lines.append("")
            lines.append(f"=== Top {top_n} classes with missed branches ===")
            lines.append("")
            lines.append("missed\tcovered\tclass")
            for missed, covered, name in gaps[:top_n]:
                lines.append(f"{missed}\t{covered}\t{name}")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            metadata={
                "overall": overall,
                "gap_count": len(gaps),
            },
        )

    return jacoco_coverage
