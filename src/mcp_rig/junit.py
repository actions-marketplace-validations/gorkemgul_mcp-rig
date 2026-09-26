"""JUnit XML output for structured MCP Rig suite results."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from mcp_rig.runner import CaseStatus, InfrastructureError, SuiteResult


def write_junit(path: str | Path, suite_name: str, result: SuiteResult) -> None:
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        name=suite_name,
        tests=str(len(result.results) + (result.suite_error is not None)),
        failures=str(result.failed),
        errors=str(result.errors),
        skipped=str(result.skipped),
        time=_seconds(sum(item.elapsed_ms for item in result.results)),
    )
    for item in result.results:
        case = ET.SubElement(
            suite,
            "testcase",
            classname=suite_name,
            name=item.name,
            time=_seconds(item.elapsed_ms),
        )
        if item.status is CaseStatus.FAILED:
            assert item.failures
            failure = ET.SubElement(case, "failure", message=item.failures[0])
            failure.text = "\n".join(item.failures)
        elif item.status is CaseStatus.ERROR:
            assert item.error is not None
            _add_error(case, item.error)
        elif item.status is CaseStatus.SKIPPED:
            assert item.skip_reason is not None
            ET.SubElement(case, "skipped", message=item.skip_reason)
    if result.suite_error is not None:
        case = ET.SubElement(
            suite,
            "testcase",
            classname=suite_name,
            name=f"[suite {result.suite_error.category}]",
            time="0.000",
        )
        _add_error(case, result.suite_error)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _add_error(case: ET.Element, error: InfrastructureError) -> None:
    element = ET.SubElement(
        case,
        "error",
        type=f"{error.category}.{error.exception_type}",
        message=error.message,
    )
    element.text = error.message


def _seconds(milliseconds: float) -> str:
    return f"{milliseconds / 1000:.3f}"
