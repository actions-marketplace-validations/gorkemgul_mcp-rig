import shlex

from mcp_rig.cli import main


def write_suite(tmp_path, fixture_spec, cases):
    command = shlex.join([fixture_spec.command, *fixture_spec.args])
    path = tmp_path / "suite.yaml"
    path.write_text(f"server: {command!r}\ntests:\n{cases}", encoding="utf-8")
    return path


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
