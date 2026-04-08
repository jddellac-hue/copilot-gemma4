"""Unit tests for the jacoco_coverage tool."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from harness.tools.jacoco import build_jacoco_tool


SAMPLE_JACOCO_XML = dedent("""\
<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
  <counter type="INSTRUCTION" missed="40" covered="160"/>
  <counter type="BRANCH" missed="10" covered="30"/>
  <counter type="LINE" missed="8" covered="42"/>
  <counter type="METHOD" missed="2" covered="18"/>
  <counter type="CLASS" missed="1" covered="9"/>
  <package name="com/example/service">
    <class name="com/example/service/PaymentService">
      <counter type="BRANCH" missed="6" covered="14"/>
    </class>
    <class name="com/example/service/UserService">
      <counter type="BRANCH" missed="3" covered="17"/>
    </class>
    <class name="com/example/service/HealthCheck">
      <counter type="BRANCH" missed="0" covered="4"/>
    </class>
  </package>
  <package name="com/example/util">
    <class name="com/example/util/StringUtils">
      <counter type="BRANCH" missed="1" covered="9"/>
    </class>
  </package>
</report>
""")


def test_jacoco_parses_report(tmp_path: Path):
    report = tmp_path / "target" / "site" / "jacoco" / "jacoco.xml"
    report.parent.mkdir(parents=True)
    report.write_text(SAMPLE_JACOCO_XML)

    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({"report_path": "target/site/jacoco/jacoco.xml"})

    assert result.ok
    assert "80.0%" in result.content  # INSTRUCTION: 160/(160+40)
    assert "75.0%" in result.content  # BRANCH: 30/(30+10)
    assert "PaymentService" in result.content
    assert "HealthCheck" not in result.content  # 0 missed branches


def test_jacoco_sorts_by_missed(tmp_path: Path):
    report = tmp_path / "jacoco.xml"
    report.write_text(SAMPLE_JACOCO_XML)

    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({"report_path": "jacoco.xml"})

    assert result.ok
    # PaymentService (6 missed) should appear before UserService (3 missed)
    idx_payment = result.content.index("PaymentService")
    idx_user = result.content.index("UserService")
    assert idx_payment < idx_user


def test_jacoco_report_not_found(tmp_path: Path):
    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({"report_path": "nonexistent/jacoco.xml"})

    assert not result.ok
    assert "not found" in result.content


def test_jacoco_path_traversal_denied(tmp_path: Path):
    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({"report_path": "../../etc/passwd"})

    assert not result.ok
    assert "traversal" in result.content


def test_jacoco_requires_report_path(tmp_path: Path):
    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({})

    assert not result.ok
    assert "report_path" in result.content


def test_jacoco_top_n(tmp_path: Path):
    report = tmp_path / "jacoco.xml"
    report.write_text(SAMPLE_JACOCO_XML)

    tool = build_jacoco_tool(tmp_path)
    result = tool.invoke({"report_path": "jacoco.xml", "top_n": 1})

    assert result.ok
    assert "PaymentService" in result.content
    # Only top 1, so UserService and StringUtils should not be in the gaps section
    gaps_section = result.content.split("missed branches")[1]
    assert "UserService" not in gaps_section
