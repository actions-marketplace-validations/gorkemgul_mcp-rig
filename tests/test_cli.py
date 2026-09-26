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
    assert "could not run server" in captured.err
    assert "Traceback" not in captured.err


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
