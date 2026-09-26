# MCP Rig Stdio Suite Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first usable `mcp-rig run` workflow: parse a YAML suite, execute tool cases against one stdio MCP server, evaluate `is_error` and `contains`, print results, and return stable exit codes.

**Architecture:** Five focused modules form a one-way pipeline from YAML configuration to normalized execution results and terminal output. The runner reuses the Phase 1 `connect()`/`Probe` boundary; parsing, assertions, and reporting remain independently testable pure or filesystem-only components.

**Tech Stack:** Python 3.11+, MCP Python SDK 2.x, PyYAML, argparse, AnyIO, pytest, Ruff, Hatchling.

**Spec:** `docs/superpowers/specs/2026-09-25-stdio-suite-execution-design.md`

## Global Constraints

- Product, distribution, and CLI name: `mcp-rig`; Python package: `mcp_rig`.
- Python 3.11 or newer.
- Only local stdio MCP servers and tools are supported.
- Runtime dependencies remain `mcp>=2.2,<3`, `pyyaml>=6`, and `jsonschema>=4`; add no runtime dependency.
- This increment supports only `is_error` and `contains` expectations.
- One server process is used per suite and cases run sequentially in YAML order.
- Invalid suites are rejected before a subprocess starts.
- Tool-level MCP errors remain assertion-visible `CallOutcome` values; infrastructure failures remain exceptions until the CLI maps them to exit code `2`.
- Do not add JUnit, `check`, HTTP/SSE, advanced assertions, release automation, or PyPI publishing.
- Development is test-first and every task finishes with its focused tests, the full suite, and Ruff.

## Review Focus

- A YAML scalar such as `command: true`, a quoted empty executable, numeric server argument, or numeric environment value must be rejected rather than silently coerced; Task 1 pins all four.
- An explicitly empty `contains: []` must be rejected because it would otherwise pass vacuously and hide a configuration mistake; Task 1 pins it.
- A missing or unreadable suite file must produce concise exit code `2` behavior without a traceback; Tasks 1 and 5 pin the boundary.
- An assertion failure must not prevent later cases from running, while an infrastructure exception must abort rather than becoming a test mismatch; Task 3 pins both paths.
- Server stderr must remain hidden by default and become visible only with `--server-logs`; Task 5 pins both modes through a real subprocess.

---

## File Structure

- `src/mcp_rig/spec.py`: YAML parsing, validation, defaults, and path resolution.
- `src/mcp_rig/assertions.py`: pure `CallOutcome` expectation checks.
- `src/mcp_rig/runner.py`: sequential orchestration and structured results.
- `src/mcp_rig/report.py`: deterministic human-readable terminal rendering.
- `src/mcp_rig/cli.py`: argparse boundary, diagnostics, and exit codes.
- `tests/test_spec.py`: parser and validation coverage.
- `tests/test_assertions.py`: pure expectation behavior.
- `tests/test_runner.py`: real stdio runner integration and infrastructure propagation.
- `tests/test_report.py`: plain and colored report rendering.
- `tests/test_cli.py`: end-to-end command behavior and exit codes.
- `examples/fixture.yaml`: runnable local example.
- `pyproject.toml`: `mcp-rig` console-script registration.
- `README.md`: current runnable workflow.

### Task 1: YAML Suite Model and Validation

**Files:**
- Create: `src/mcp_rig/spec.py`
- Create: `tests/test_spec.py`

**Interfaces:**
- Consumes: `mcp_rig.client.ServerSpec` and PyYAML `safe_load`.
- Produces: `SpecError`, `Case(name, call, args, expect)`, `Suite(path, server, cases)`, and `load_suite(path) -> Suite`.

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_spec.py`:

```python
from pathlib import Path

import pytest

from mcp_rig.spec import SpecError, load_suite


def write_suite(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "suite.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_string_server_and_defaults(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            """
server: python server.py
tests:
  - name: adds
    call: add
    args: {a: 1, b: 2}
    expect: {contains: "3"}
""",
        )
    )

    assert suite.path == tmp_path / "suite.yaml"
    assert suite.server.command == "python"
    assert suite.server.args == ["server.py"]
    assert suite.server.cwd == str(tmp_path.resolve())
    assert suite.cases[0].args == {"a": 1, "b": 2}


def test_loads_mapping_server_and_resolves_relative_cwd(tmp_path):
    suite = load_suite(
        write_suite(
            tmp_path,
            """
server:
  command: python -u
  args: [server.py]
  env: {MODE: test}
  cwd: fixtures
tests:
  - name: pings
    call: ping
""",
        )
    )

    assert suite.server.command == "python"
    assert suite.server.args == ["-u", "server.py"]
    assert suite.server.env == {"MODE": "test"}
    assert suite.server.cwd == str((tmp_path / "fixtures").resolve())
    assert suite.cases[0].args == {}
    assert suite.cases[0].expect == {}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("- not-a-mapping", "top level must be a mapping"),
        ("tests: []", "'server'"),
        ("server: python server.py", "'tests' must be a non-empty list"),
        ("server: python server.py\ntests: []", "'tests' must be a non-empty list"),
        ("server: python server.py\ntests: [{call: ping}]", "'name'"),
        ("server: python server.py\ntests: [{name: ping}]", "'call'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, args: []}]", "'args'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {other: true}}]", "unknown expect keys"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {is_error: nope}}]", "'is_error'"),
        ("server: python server.py\ntests: [{name: ping, call: ping, expect: {contains: []}}]", "'contains'"),
        ("server: {command: true}\ntests: [{name: ping, call: ping}]", "'command'"),
        ("server: '\"\"'\ntests: [{name: ping, call: ping}]", "server command is empty"),
        ("server: {command: python, args: [server.py, 3]}\ntests: [{name: ping, call: ping}]", "'args'"),
        ("server: {command: python, env: {PORT: 3}}\ntests: [{name: ping, call: ping}]", "'env'"),
        ("server: [unclosed", "invalid YAML"),
    ],
)
def test_rejects_invalid_suites(tmp_path, body, message):
    with pytest.raises(SpecError, match=message):
        load_suite(write_suite(tmp_path, body))


def test_missing_file_is_a_spec_error(tmp_path):
    with pytest.raises(SpecError, match="could not read"):
        load_suite(tmp_path / "missing.yaml")
```

- [ ] **Step 2: Run the parser tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_spec.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.spec'`.

- [ ] **Step 3: Implement strict YAML parsing**

Create `src/mcp_rig/spec.py`:

```python
"""Load and validate MCP Rig YAML suites."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mcp_rig.client import ServerSpec

KNOWN_EXPECT_KEYS = {"is_error", "contains"}


class SpecError(ValueError):
    """Raised when a suite file cannot be loaded as valid configuration."""


@dataclass(frozen=True)
class Case:
    name: str
    call: str
    args: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Suite:
    path: Path
    server: ServerSpec
    cases: list[Case]


def load_suite(path: str | Path) -> Suite:
    suite_path = Path(path)
    try:
        text = suite_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"{suite_path}: could not read suite: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{suite_path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{suite_path}: top level must be a mapping")

    server = _parse_server(data.get("server"), suite_path)
    raw_cases = data.get("tests")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SpecError(f"{suite_path}: 'tests' must be a non-empty list")
    cases = [_parse_case(raw, index, suite_path) for index, raw in enumerate(raw_cases)]
    return Suite(path=suite_path, server=server, cases=cases)


def _parse_server(raw: Any, path: Path) -> ServerSpec:
    if isinstance(raw, str) and raw.strip():
        try:
            spec = ServerSpec.from_command_line(raw)
        except ValueError as exc:
            raise SpecError(f"{path}: invalid 'server': {exc}") from exc
        if not spec.command:
            raise SpecError(f"{path}: invalid 'server': server command is empty")
    elif isinstance(raw, dict):
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise SpecError(f"{path}: 'server.command' must be a non-empty string")
        args = raw.get("args", [])
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise SpecError(f"{path}: 'server.args' must be a list of strings")
        env = raw.get("env")
        if env is not None and (
            not isinstance(env, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())
        ):
            raise SpecError(f"{path}: 'server.env' must map strings to strings")
        cwd = raw.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise SpecError(f"{path}: 'server.cwd' must be a string")
        try:
            spec = ServerSpec.from_command_line(command)
        except ValueError as exc:
            raise SpecError(f"{path}: invalid 'server.command': {exc}") from exc
        spec.args.extend(args)
        spec.env = env
        spec.cwd = cwd
    else:
        raise SpecError(f"{path}: 'server' must be a command string or mapping")

    base = path.parent.resolve()
    if spec.cwd is None:
        spec.cwd = str(base)
    else:
        cwd_path = Path(spec.cwd)
        spec.cwd = str(cwd_path if cwd_path.is_absolute() else (base / cwd_path).resolve())
    return spec


def _parse_case(raw: Any, index: int, path: Path) -> Case:
    where = f"{path}: tests[{index}]"
    if not isinstance(raw, dict):
        raise SpecError(f"{where} must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SpecError(f"{where}: 'name' must be a non-empty string")
    call = raw.get("call")
    if not isinstance(call, str) or not call.strip():
        raise SpecError(f"{where} ({name}): 'call' must be a non-empty string")
    args = raw.get("args", {})
    if not isinstance(args, dict):
        raise SpecError(f"{where} ({name}): 'args' must be a mapping")
    expect = raw.get("expect", {})
    if not isinstance(expect, dict):
        raise SpecError(f"{where} ({name}): 'expect' must be a mapping")
    unknown = set(expect) - KNOWN_EXPECT_KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise SpecError(f"{where} ({name}): unknown expect keys: {names}")
    if "is_error" in expect and not isinstance(expect["is_error"], bool):
        raise SpecError(f"{where} ({name}): 'is_error' must be a boolean")
    if "contains" in expect:
        contains = expect["contains"]
        valid = isinstance(contains, str) or (
            isinstance(contains, list)
            and bool(contains)
            and all(isinstance(value, str) for value in contains)
        )
        if not valid:
            raise SpecError(f"{where} ({name}): 'contains' must be a string or non-empty list of strings")
    return Case(name=name, call=call, args=args, expect=expect)
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_spec.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: `tests/test_spec.py` reports `18 passed`; the full suite passes; Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the parser**

```bash
git add src/mcp_rig/spec.py tests/test_spec.py
git commit -m "feat: load validated YAML suites"
```

### Task 2: Minimal Assertion Engine

**Files:**
- Create: `src/mcp_rig/assertions.py`
- Create: `tests/test_assertions.py`

**Interfaces:**
- Consumes: `CallOutcome` and validated expectation mappings from Task 1.
- Produces: `check(expect: dict[str, Any], outcome: CallOutcome) -> list[str]`.

- [ ] **Step 1: Write the failing assertion tests**

Create `tests/test_assertions.py`:

```python
from mcp_rig.assertions import check
from mcp_rig.client import CallOutcome


def outcome(text="", is_error=False, structured=None, latency_ms=10.0):
    return CallOutcome(is_error=is_error, text=text, structured=structured, latency_ms=latency_ms)


def test_empty_expect_requires_success():
    assert check({}, outcome("ok")) == []
    assert check({}, outcome("boom", is_error=True)) == [
        "is_error: expected False, got True (text: 'boom')"
    ]


def test_explicit_error_expectation():
    assert check({"is_error": True}, outcome("boom", is_error=True)) == []
    assert check({"is_error": True}, outcome("ok")) == [
        "is_error: expected True, got False (text: 'ok')"
    ]


def test_contains_accepts_one_string():
    assert check({"contains": "Ada"}, outcome("Hello Ada")) == []
    assert check({"contains": "Ada"}, outcome("Hello Lin")) == [
        "contains: 'Ada' not found in 'Hello Lin'"
    ]


def test_contains_requires_every_string_in_a_list():
    assert check({"contains": ["21", "sunny"]}, outcome("21°C and sunny")) == []
    assert check({"contains": ["21", "rain"]}, outcome("21°C and sunny")) == [
        "contains: 'rain' not found in '21°C and sunny'"
    ]


def test_reports_every_failed_expectation():
    failures = check({"is_error": True, "contains": ["Ada", "admin"]}, outcome("Lin"))
    assert failures == [
        "is_error: expected True, got False (text: 'Lin')",
        "contains: 'Ada' not found in 'Lin'",
        "contains: 'admin' not found in 'Lin'",
    ]


def test_long_text_is_shortened_in_failure_messages():
    [failure] = check({"contains": "missing"}, outcome("a" * 200))
    assert "…" in failure
    assert len(failure) < 150
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_assertions.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.assertions'`.

- [ ] **Step 3: Implement only `is_error` and `contains`**

Create `src/mcp_rig/assertions.py`:

```python
"""Compare normalized tool outcomes with suite expectations."""

from __future__ import annotations

from typing import Any

from mcp_rig.client import CallOutcome


def check(expect: dict[str, Any], outcome: CallOutcome) -> list[str]:
    failures: list[str] = []
    expected_error = expect.get("is_error", False)
    if outcome.is_error != expected_error:
        failures.append(
            f"is_error: expected {expected_error}, got {outcome.is_error} "
            f"(text: {_short(outcome.text)})"
        )
    for needle in _needles(expect.get("contains")):
        if needle not in outcome.text:
            failures.append(f"contains: {needle!r} not found in {_short(outcome.text)}")
    return failures


def _needles(value: Any) -> list[str]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _short(text: str, limit: int = 80) -> str:
    shortened = text if len(text) <= limit else text[:limit] + "…"
    return repr(shortened)
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_assertions.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: `tests/test_assertions.py` reports `6 passed`; the full suite passes; Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the assertion engine**

```bash
git add src/mcp_rig/assertions.py tests/test_assertions.py
git commit -m "feat: evaluate core suite expectations"
```

### Task 3: Sequential Suite Runner

**Files:**
- Create: `src/mcp_rig/runner.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- Consumes: `Suite`, `Case`, `connect`, `Probe`, `CallOutcome`, and `check`.
- Produces: `CaseResult`, `SuiteResult`, and `async run_suite(suite, show_server_logs=False) -> SuiteResult`.

- [ ] **Step 1: Write failing real-stdio runner tests**

Create `tests/test_runner.py`:

```python
import pytest

from mcp_rig.client import ServerSpec
from mcp_rig.runner import run_suite
from mcp_rig.spec import Case, Suite


@pytest.mark.anyio
async def test_runs_all_cases_in_order_after_an_assertion_failure(fixture_spec, tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=fixture_spec,
        cases=[
            Case("adds", "add", {"a": 2, "b": 2}, {"contains": "4"}),
            Case("wrong on purpose", "echo", {"text": "hi"}, {"contains": "bye"}),
            Case("still runs", "echo", {"text": "after"}, {"contains": "after"}),
        ],
    )

    result = await run_suite(suite)

    assert [item.name for item in result.results] == ["adds", "wrong on purpose", "still runs"]
    assert [item.passed for item in result.results] == [True, False, True]
    assert result.results[1].failures == ["contains: 'bye' not found in 'hi'"]
    assert (result.passed, result.failed, result.ok) == (2, 1, False)
    assert all(item.outcome is not None for item in result.results)


@pytest.mark.anyio
async def test_tool_error_can_be_an_expected_passing_result(fixture_spec, tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=fixture_spec,
        cases=[Case("missing user", "get_user", {"user_id": 99}, {"is_error": True, "contains": "not found"})],
    )

    result = await run_suite(suite)

    assert result.ok is True
    assert result.results[0].outcome.is_error is True


@pytest.mark.anyio
async def test_infrastructure_failure_propagates(tmp_path):
    suite = Suite(
        path=tmp_path / "suite.yaml",
        server=ServerSpec("/definitely/missing/mcp-rig-server"),
        cases=[Case("never runs", "echo")],
    )

    with pytest.raises(OSError):
        await run_suite(suite)
```

- [ ] **Step 2: Run the runner tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_runner.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.runner'`.

- [ ] **Step 3: Implement sequential orchestration**

Create `src/mcp_rig/runner.py`:

```python
"""Run suite cases sequentially against one MCP server process."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_rig.assertions import check
from mcp_rig.client import CallOutcome, Probe, connect
from mcp_rig.spec import Case, Suite


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    failures: list[str]
    outcome: CallOutcome


@dataclass(frozen=True)
class SuiteResult:
    results: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(item.passed for item in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0


async def run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult:
    results: list[CaseResult] = []
    async with connect(suite.server, show_server_logs=show_server_logs) as probe:
        for case in suite.cases:
            results.append(await _run_case(probe, case))
    return SuiteResult(results)


async def _run_case(probe: Probe, case: Case) -> CaseResult:
    outcome = await probe.call(case.call, case.args)
    failures = check(case.expect, outcome)
    return CaseResult(
        name=case.name,
        passed=not failures,
        failures=failures,
        outcome=outcome,
    )
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_runner.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: `tests/test_runner.py` reports `3 passed`; the full suite passes; Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the runner**

```bash
git add src/mcp_rig/runner.py tests/test_runner.py
git commit -m "feat: execute stdio suites sequentially"
```

### Task 4: Terminal Report

**Files:**
- Create: `src/mcp_rig/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: `SuiteResult` and per-case latency from `CaseResult.outcome`.
- Produces: `render_suite(title, result, color=False) -> str` and ANSI color constants.

- [ ] **Step 1: Write failing rendering tests**

Create `tests/test_report.py`:

```python
from mcp_rig.client import CallOutcome
from mcp_rig.report import render_suite
from mcp_rig.runner import CaseResult, SuiteResult


def result(name, passed, failures, latency_ms):
    return CaseResult(name, passed, failures, CallOutcome(False, "", None, latency_ms))


def test_render_suite_plain_text():
    suite_result = SuiteResult(
        [
            result("adds", True, [], 12.4),
            result("breaks", False, ["contains: 'x' not found in 'y'"], 2.2),
        ]
    )

    assert render_suite("suite.yaml", suite_result) == "\n".join(
        [
            "MCP Rig — suite.yaml",
            "",
            "✓ adds (12 ms)",
            "✗ breaks (2 ms)",
            "    contains: 'x' not found in 'y'",
            "",
            "1 passed, 1 failed",
        ]
    )


def test_render_suite_color_wraps_only_status_marks():
    text = render_suite("suite.yaml", SuiteResult([result("adds", True, [], 1.0)]), color=True)

    assert "\033[32m✓\033[0m adds" in text
    assert "MCP Rig — suite.yaml" in text
```

- [ ] **Step 2: Run the report tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_report.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.report'`.

- [ ] **Step 3: Implement deterministic reporting**

Create `src/mcp_rig/report.py`:

```python
"""Render MCP Rig suite results for humans."""

from __future__ import annotations

from mcp_rig.runner import SuiteResult

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_suite(title: str, result: SuiteResult, color: bool = False) -> str:
    lines = [f"MCP Rig — {title}", ""]
    for item in result.results:
        mark = _paint("✓", GREEN, color) if item.passed else _paint("✗", RED, color)
        lines.append(f"{mark} {item.name} ({item.outcome.latency_ms:.0f} ms)")
        lines.extend(f"    {failure}" for failure in item.failures)
    lines.extend(["", f"{result.passed} passed, {result.failed} failed"])
    return "\n".join(lines)
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_report.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: `tests/test_report.py` reports `2 passed`; the full suite passes; Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the report renderer**

```bash
git add src/mcp_rig/report.py tests/test_report.py
git commit -m "feat: render stdio suite results"
```

### Task 5: Public `mcp-rig run` Command

**Files:**
- Create: `src/mcp_rig/cli.py`
- Create: `tests/test_cli.py`
- Create: `examples/fixture.yaml`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `load_suite`, `SpecError`, `run_suite`, and `render_suite`.
- Produces: `main(argv=None) -> int`, console command `mcp-rig`, `--server-logs`, and exit constants `EXIT_OK=0`, `EXIT_FAILED=1`, `EXIT_USAGE=2`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the CLI tests and verify the module is missing**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.cli'`.

- [ ] **Step 3: Implement the CLI boundary**

Create `src/mcp_rig/cli.py`:

```python
"""Command-line entry point for MCP Rig."""

from __future__ import annotations

import argparse
import sys

import anyio

from mcp_rig.report import render_suite
from mcp_rig.runner import run_suite
from mcp_rig.spec import SpecError, load_suite

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-rig",
        description="Deterministic tests for MCP servers.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run a YAML tool suite")
    run_parser.add_argument("suite", help="path to a YAML suite")
    run_parser.add_argument(
        "--server-logs",
        action="store_true",
        help="show the MCP server's stderr",
    )

    args = parser.parse_args(argv)
    return _run(args, color=sys.stdout.isatty())


def _run(args: argparse.Namespace, color: bool) -> int:
    try:
        suite = load_suite(args.suite)
        result = anyio.run(run_suite, suite, args.server_logs)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - CLI converts infrastructure errors to exit 2
        print(f"error: {args.suite}: could not run server: {_describe(exc)}", file=sys.stderr)
        return EXIT_USAGE

    print(render_suite(args.suite, result, color=color))
    return EXIT_OK if result.ok else EXIT_FAILED


def _describe(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"
```

- [ ] **Step 4: Register the console script**

Add this block to `pyproject.toml` immediately after `[project]` metadata and dependencies:

```toml
[project.scripts]
mcp-rig = "mcp_rig.cli:main"
```

Reinstall the editable project so `.venv/bin/mcp-rig` is generated:

```bash
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 5: Add the runnable example and README usage**

Create `examples/fixture.yaml`:

```yaml
# From the repository root: mcp-rig run examples/fixture.yaml
server: python ../tests/fixtures/fixture_server.py

tests:
  - name: adds two numbers
    call: add
    args: {a: 2, b: 3}
    expect:
      contains: "5"

  - name: unknown user returns an error
    call: get_user
    args: {user_id: 42}
    expect:
      is_error: true
      contains: "not found"
```

Replace `README.md` with:

````markdown
# MCP Rig

Deterministic, CI-friendly testing for Model Context Protocol servers.

MCP Rig currently launches local MCP servers over stdio and runs declarative
tool suites in YAML.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run a suite

```bash
mcp-rig run examples/fixture.yaml
```

Each case expects a successful tool call unless it declares
`is_error: true`. The `contains` expectation accepts one string or a list of
strings. Add `--server-logs` to expose the MCP server's stderr while
diagnosing startup or tool behavior.

This release supports local stdio servers and tools only. Advanced
assertions, JUnit output, protocol checks, and PyPI publication arrive in
later increments.
````

- [ ] **Step 6: Run focused, complete, and installed-command verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mcp-rig --help
.venv/bin/mcp-rig run examples/fixture.yaml
```

Expected: `tests/test_cli.py` reports `5 passed`; the full suite passes; Ruff reports `All checks passed!`; help lists `run`; the example reports `2 passed, 0 failed` and exits `0`.

- [ ] **Step 7: Commit the public workflow**

```bash
git add pyproject.toml README.md examples/fixture.yaml src/mcp_rig/cli.py tests/test_cli.py
git commit -m "feat: add YAML stdio suite command"
```

## Completion Review

After Task 5, compare the complete diff with `docs/superpowers/specs/2026-09-25-stdio-suite-execution-design.md` and confirm:

- Only `is_error` and `contains` expectations exist.
- Invalid YAML and configuration fail before `connect()` is called.
- One server connection encloses the complete sequential case loop.
- Assertion failures continue to later cases; infrastructure failures propagate to the CLI.
- Reports contain every case, failure details, and summary counts.
- CLI exit codes are `0` for all pass, `1` for assertion failure, and `2` for usage/configuration/infrastructure failure.
- `--server-logs` is the only way server stderr becomes visible.
- No JUnit, `check`, remote transport, or release work was added.
- Full pytest, Ruff, installed help, and the example suite all pass.

Stop after this review. Do not begin the next increment without explicit approval.
