import shlex
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

import mcp_rig.cli as cli_module
from mcp_rig.cli import main
from mcp_rig.client import CallOutcome, ToolInfo


def write_suite(tmp_path, fixture_spec, cases):
    command = shlex.join([fixture_spec.command, *fixture_spec.args])
    path = tmp_path / "suite.yaml"
    path.write_text(f"server: {command!r}\ntests:\n{cases}", encoding="utf-8")
    return path


def server_command(spec):
    return shlex.join([spec.command, *spec.args])


PASSING = """\
  - name: adds
    call: add
    args: {a: 1, b: 1}
    expect: {contains: "2"}
"""

FAILING = PASSING + """\
  - name: wrong
    call: echo
    args: {text: hi}
    expect: {contains: bye}
"""


def test_run_passing_suite_exits_zero(tmp_path, fixture_spec, capsys):
    code = main(["run", str(write_suite(tmp_path, fixture_spec, PASSING))])

    captured = capsys.readouterr()
    assert code == 0
    assert "✓ adds" in captured.out
    assert "1 passed, 0 failed" in captured.out
    assert "\033[" not in captured.out


def test_run_failing_suite_exits_one_and_reports_all_cases(tmp_path, fixture_spec, capsys):
    code = main(["run", str(write_suite(tmp_path, fixture_spec, FAILING))])

    captured = capsys.readouterr()
    assert code == 1
    assert "✓ adds" in captured.out
    assert "✗ wrong" in captured.out
    assert "1 passed, 1 failed" in captured.out


def test_run_invalid_or_missing_suite_exits_two(tmp_path, capsys):
    missing = tmp_path / "missing.yaml"

    assert main(["run", str(missing)]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_run_unstartable_server_exits_two(tmp_path, capsys):
    path = tmp_path / "suite.yaml"
    path.write_text(
        "server: /definitely/missing/mcp-rig-server\n"
        "tests:\n  - {name: never, call: echo}\n",
        encoding="utf-8",
    )

    assert main(["run", str(path)]) == 2
    captured = capsys.readouterr()
    assert "! suite setup:" in captured.out
    assert "- never" in captured.out
    assert "suite could not start" in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_server_logs_are_hidden_by_default_and_visible_with_flag(tmp_path, fixture_spec, capfd):
    cases = """\
  - name: writes log
    call: write_stderr
    args: {message: mcp-rig-cli-server-log}
    expect: {contains: written}
"""
    path = write_suite(tmp_path, fixture_spec, cases)

    assert main(["run", str(path)]) == 0
    assert "mcp-rig-cli-server-log" not in capfd.readouterr().err
    assert main(["run", str(path), "--server-logs"]) == 0
    assert "mcp-rig-cli-server-log" in capfd.readouterr().err


def test_run_advanced_expectations_through_public_cli(tmp_path, fixture_spec, capsys):
    cases = """\
  - name: validates user payload
    call: get_user
    args: {user_id: 1}
    expect:
      is_error: false
      contains: Ada
      not_contains: password
      matches: Ada
      max_latency_ms: 5000
      json_path:
        name: Ada
        roles.0: admin
      schema:
        type: object
        required: [id, name, roles]
        properties:
          id: {type: integer}
          name: {type: string}
          roles: {type: array}
"""
    path = write_suite(tmp_path, fixture_spec, cases)

    assert main(["run", str(path)]) == 0
    captured = capsys.readouterr()
    assert "✓ validates user payload" in captured.out
    assert "1 passed, 0 failed" in captured.out


def test_run_timeout_exits_two_and_reports_skipped_cases(tmp_path, fixture_spec, capsys):
    cases = """\
  - name: too slow
    call: slow
    args: {seconds: 0.2}
    timeout_s: 0.01
  - name: never runs
    call: echo
    args: {text: after}
"""
    path = write_suite(tmp_path, fixture_spec, cases)

    assert main(["run", str(path)]) == 2
    captured = capsys.readouterr()
    assert "! too slow" in captured.out
    assert "- never runs" in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_run_writes_passing_junit_report(tmp_path, fixture_spec, capsys):
    suite_path = write_suite(tmp_path, fixture_spec, PASSING)
    report_path = tmp_path / "results.xml"

    assert main(["run", str(suite_path), "--junit", str(report_path)]) == 0
    captured = capsys.readouterr()
    suite = ET.parse(report_path).getroot().find("testsuite")
    assert suite is not None
    assert suite.attrib["failures"] == "0"
    assert suite.attrib["errors"] == "0"
    assert "✓ adds" in captured.out


def test_run_writes_failing_junit_report_and_exits_one(tmp_path, fixture_spec, capsys):
    suite_path = write_suite(tmp_path, fixture_spec, FAILING)
    report_path = tmp_path / "results.xml"

    assert main(["run", str(suite_path), "--junit", str(report_path)]) == 1
    captured = capsys.readouterr()
    suite = ET.parse(report_path).getroot().find("testsuite")
    assert suite is not None
    failure = suite.findall("testcase")[1].find("failure")
    assert failure is not None
    assert "contains: 'bye' not found in 'hi'" in failure.text
    assert "✗ wrong" in captured.out


def test_run_writes_timeout_and_skipped_junit_results(tmp_path, fixture_spec):
    cases = """\
  - name: too slow
    call: slow
    args: {seconds: 0.2}
    timeout_s: 0.01
  - name: never runs
    call: echo
    args: {text: after}
"""
    suite_path = write_suite(tmp_path, fixture_spec, cases)
    report_path = tmp_path / "results.xml"

    assert main(["run", str(suite_path), "--junit", str(report_path)]) == 2
    suite = ET.parse(report_path).getroot().find("testsuite")
    assert suite is not None
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["skipped"] == "1"
    first, second = suite.findall("testcase")
    assert first.find("error") is not None
    assert second.find("skipped") is not None


def test_run_writes_setup_error_junit_report(tmp_path):
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "server: /definitely/missing/mcp-rig-server\n"
        "tests:\n  - {name: never, call: echo}\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "results.xml"

    assert main(["run", str(suite_path), "--junit", str(report_path)]) == 2
    suite = ET.parse(report_path).getroot().find("testsuite")
    assert suite is not None
    cases = suite.findall("testcase")
    assert [case.attrib["name"] for case in cases] == ["never", "[suite setup]"]
    assert cases[0].find("skipped") is not None
    assert cases[1].find("error") is not None


def test_invalid_configuration_does_not_create_junit_report(tmp_path, capsys):
    report_path = tmp_path / "results.xml"

    assert main(["run", str(tmp_path / "missing.yaml"), "--junit", str(report_path)]) == 2
    captured = capsys.readouterr()
    assert not report_path.exists()
    assert "error:" in captured.err


def test_unwritable_junit_path_exits_two_after_printing_terminal_result(tmp_path, fixture_spec, capsys):
    suite_path = write_suite(tmp_path, fixture_spec, PASSING)
    report_path = tmp_path / "missing" / "results.xml"

    assert main(["run", str(suite_path), "--junit", str(report_path)]) == 2
    captured = capsys.readouterr()
    assert "✓ adds" in captured.out
    assert "could not write JUnit report" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_junit_path_cannot_overwrite_suite_file(tmp_path, capsys):
    suite_path = tmp_path / "suite.yaml"
    original = (
        "server: /definitely/missing/mcp-rig-server\n"
        "tests:\n  - {name: never, call: echo}\n"
    )
    suite_path.write_text(original, encoding="utf-8")

    assert main(["run", str(suite_path), "--junit", str(suite_path)]) == 2
    captured = capsys.readouterr()
    assert suite_path.read_text(encoding="utf-8") == original
    assert "JUnit report path must differ from suite path" in captured.err
    assert "could not run server" not in captured.err


def test_invalid_advanced_expectation_fails_before_server_startup(tmp_path, capsys):
    path = tmp_path / "suite.yaml"
    path.write_text(
        "server: /definitely/missing/mcp-rig-server\n"
        "tests:\n"
        "  - name: never\n"
        "    call: echo\n"
        "    expect:\n"
        "      matches: '[unclosed'\n",
        encoding="utf-8",
    )

    assert main(["run", str(path)]) == 2
    captured = capsys.readouterr()
    assert "invalid 'matches' regular expression" in captured.err
    assert "could not run server" not in captured.err
    assert "Traceback" not in captured.err


def test_check_passes_with_lint_warnings(fixture_spec, capsys):
    code = main(["check", server_command(fixture_spec)])

    captured = capsys.readouterr()
    assert code == 0
    assert "✓ lists tools" in captured.out
    assert "✓ unknown tool returns an error" in captured.out
    assert "✓ server alive after bad calls" in captured.out
    assert "undocumented [no-description]" in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_check_strict_fails_on_lint_warnings(fixture_spec, capsys):
    code = main(["check", server_command(fixture_spec), "--strict"])

    captured = capsys.readouterr()
    assert code == 1
    assert "3/3 checks passed" in captured.out
    assert "undocumented [no-description]" in captured.out


def test_check_probe_invalid_args_reports_required_argument_checks(fixture_spec, capsys):
    code = main(
        [
            "check",
            server_command(fixture_spec),
            "--probe-invalid-args",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "✓ add: missing required args rejected" in captured.out
    assert "✓ get_user: missing required args rejected" in captured.out


def test_check_empty_server_command_exits_two_without_traceback(capsys):
    code = main(["check", ""])

    captured = capsys.readouterr()
    assert code == 2
    assert "error:" in captured.err
    assert "server command is empty" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_check_unstartable_server_exits_two_without_traceback(capsys):
    code = main(["check", "/definitely/missing/mcp-rig-server"])

    captured = capsys.readouterr()
    assert code == 2
    assert "error:" in captured.err
    assert "could not run server" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_check_server_logs_are_hidden_by_default_and_visible_with_flag(
    fixture_spec,
    capfd,
):
    wrapper = Path(__file__).parent / "fixtures" / "stderr_server.py"
    command = shlex.join([fixture_spec.command, str(wrapper)])

    assert main(["check", command]) == 0
    assert "mcp-rig-check-server-log" not in capfd.readouterr().err

    assert main(["check", command, "--server-logs"]) == 0
    assert "mcp-rig-check-server-log" in capfd.readouterr().err


@pytest.mark.parametrize(("strict", "expected_code"), [(False, 0), (True, 1)])
def test_check_handles_valid_boolean_property_schema(
    monkeypatch,
    capsys,
    strict,
    expected_code,
):
    class BooleanSchemaProbe:
        async def list_tools(self):
            return [
                ToolInfo(
                    "boolean_property",
                    "Return a value accepted by the schema.",
                    {"type": "object", "properties": {"value": True}},
                )
            ]

        async def call(self, name, args=None, timeout_s=30.0):
            return CallOutcome(True, "unknown tool", None, 1.0)

    @asynccontextmanager
    async def fake_connect(spec, show_server_logs=False):
        yield BooleanSchemaProbe()

    monkeypatch.setattr(cli_module, "connect", fake_connect)
    argv = ["check", "fixture-server"]
    if strict:
        argv.append("--strict")

    code = main(argv)

    captured = capsys.readouterr()
    assert code == expected_code
    assert "3/3 checks passed, 1 lint warning" in captured.out
    assert "boolean_property [param-no-description]" in captured.out
    assert "error:" not in captured.err
