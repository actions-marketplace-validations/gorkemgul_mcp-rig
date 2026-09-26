import xml.etree.ElementTree as ET

import pytest

from mcp_rig.junit import write_junit
from mcp_rig.runner import CaseResult, CaseStatus, ErrorCategory, InfrastructureError, SuiteResult


def test_write_junit_represents_every_status_and_suite_error(tmp_path):
    output = tmp_path / "results.xml"
    result = SuiteResult(
        [
            CaseResult(name="passes", status=CaseStatus.PASSED, elapsed_ms=1500.0),
            CaseResult(
                name="fails",
                status=CaseStatus.FAILED,
                elapsed_ms=250.0,
                failures=["first problem", "second problem"],
            ),
            CaseResult(
                name="errors",
                status=CaseStatus.ERROR,
                elapsed_ms=10.0,
                error=InfrastructureError(ErrorCategory.TRANSPORT, "BrokenPipeError", "connection lost"),
            ),
            CaseResult(name="skips", status=CaseStatus.SKIPPED, skip_reason="session unavailable"),
        ],
        suite_error=InfrastructureError(ErrorCategory.TEARDOWN, "RuntimeError", "close failed"),
    )

    write_junit(output, "suite.yaml", result)

    root = ET.parse(output).getroot()
    assert root.tag == "testsuites"
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.attrib == {
        "name": "suite.yaml",
        "tests": "5",
        "failures": "1",
        "errors": "2",
        "skipped": "1",
        "time": "1.760",
    }
    cases = suite.findall("testcase")
    assert [case.attrib["name"] for case in cases] == [
        "passes",
        "fails",
        "errors",
        "skips",
        "[suite teardown]",
    ]
    assert [case.attrib["time"] for case in cases] == ["1.500", "0.250", "0.010", "0.000", "0.000"]
    assert cases[0].find("failure") is None
    failure = cases[1].find("failure")
    assert failure is not None
    assert failure.attrib == {"message": "first problem"}
    assert failure.text == "first problem\nsecond problem"
    error = cases[2].find("error")
    assert error is not None
    assert error.attrib == {"type": "transport.BrokenPipeError", "message": "connection lost"}
    assert error.text == "connection lost"
    skipped = cases[3].find("skipped")
    assert skipped is not None
    assert skipped.attrib == {"message": "session unavailable"}
    suite_error = cases[4].find("error")
    assert suite_error is not None
    assert suite_error.attrib == {"type": "teardown.RuntimeError", "message": "close failed"}
    assert suite_error.text == "close failed"


def test_write_junit_escapes_xml_content(tmp_path):
    output = tmp_path / "escaped.xml"
    result = SuiteResult(
        [
            CaseResult(
                name='case <one> & "two"',
                status=CaseStatus.FAILED,
                failures=['expected <tag> & "value"'],
            )
        ]
    )

    write_junit(output, 'suite <one> & "two"', result)

    suite = ET.parse(output).getroot().find("testsuite")
    assert suite is not None
    case = suite.find("testcase")
    assert suite.attrib["name"] == 'suite <one> & "two"'
    assert case is not None
    assert case.attrib["name"] == 'case <one> & "two"'
    failure = case.find("failure")
    assert failure is not None
    assert failure.attrib["message"] == 'expected <tag> & "value"'
    assert failure.text == 'expected <tag> & "value"'


def test_write_junit_propagates_file_errors(tmp_path):
    with pytest.raises(OSError):
        write_junit(tmp_path / "missing" / "results.xml", "suite.yaml", SuiteResult([]))
