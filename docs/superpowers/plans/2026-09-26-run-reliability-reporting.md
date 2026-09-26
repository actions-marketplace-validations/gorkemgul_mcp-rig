# MCP Rig Run Reliability and Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `mcp-rig run` validated per-case timeouts, explicit infrastructure-error semantics, accurate terminal/JUnit reporting, and stable exit codes.

**Architecture:** Extend the suite model with validated timeout configuration, then make the runner the sole owner of runtime status and exception normalization. Terminal and JUnit reporters consume structured results without inspecting SDK exceptions; the CLI only coordinates parsing, execution, output, and exit-code precedence.

**Tech Stack:** Python 3.11+, AnyIO, MCP Python SDK 2.x, PyYAML, `dataclasses`, `enum.StrEnum`, `xml.etree.ElementTree`, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-26-run-reliability-reporting-design.md`

## Global Constraints

- Keep the public command as one suite path: `mcp-rig run SUITE`.
- Default `timeout_s` is exactly `30.0`; accepted values are finite positive integers or floats, excluding booleans.
- One stdio server process and one initialized session serve the complete suite.
- Assertion mismatches are failures; timeout, setup, transport, teardown, and report-write problems are infrastructure errors.
- Do not continue tool calls or restart the server after a timeout or broken transport; later cases become skipped.
- Preserve tool-level MCP errors as `CallOutcome(is_error=True)` rather than infrastructure errors.
- Exit codes remain `0` success, `1` assertion failure only, and `2` configuration or infrastructure failure.
- JUnit output uses only the Python standard library and does not create missing parent directories.
- Do not add multiple-suite execution, `check`, remote transports, retries, CI/release automation, or PyPI publication.

## Review Focus

- `timeout_s: true`, NaN, and infinities must be rejected before server startup; Task 1 pins every numeric edge.
- A timeout nested anywhere in an `ExceptionGroup` must still classify as `timeout`, while `KeyboardInterrupt` must propagate; Task 2 pins both paths.
- An earlier assertion failure must remain failed when a later transport error aborts the suite, and untouched later cases must be skipped; Task 2 pins the mixed-status sequence.
- Setup and teardown failures must preserve declared/completed cases and contribute exactly one suite-level error; Task 3 pins both lifecycle boundaries.
- XML-reserved characters must round-trip through JUnit, and an unwritable report path must return exit 2 without hiding the terminal result; Tasks 4 and 5 pin these output failures.

---

## File Structure

- Modify `src/mcp_rig/spec.py`: store and validate per-case timeout configuration.
- Modify `src/mcp_rig/runner.py`: define statuses, normalized infrastructure errors, result counts, and interruption behavior.
- Modify `src/mcp_rig/report.py`: render passed, failed, error, skipped, setup, and teardown states.
- Create `src/mcp_rig/junit.py`: serialize structured suite results as deterministic JUnit XML.
- Modify `src/mcp_rig/cli.py`: expose `--junit`, write reports, and enforce exit-code precedence.
- Modify `tests/test_spec.py`: cover timeout parsing and validation.
- Modify `tests/test_runner.py`: cover timeout propagation, abort behavior, and lifecycle failures.
- Modify `tests/test_report.py`: cover all terminal result states and counts.
- Create `tests/test_junit.py`: cover XML structure, counts, content, and escaping.
- Modify `tests/test_cli.py`: cover public timeout, infrastructure, JUnit, and exit-code behavior.
- Modify `README.md`: document timeouts, JUnit, statuses, and exit codes.
- Modify `examples/fixture.yaml`: demonstrate an explicit timeout.

### Task 1: Validate Per-Case Timeouts

**Files:**
- Modify: `src/mcp_rig/spec.py:34-40,114-179`
- Modify: `tests/test_spec.py`

**Interfaces:**
- Consumes: existing `load_suite(path: str | Path) -> Suite` and `_parse_case(raw, index, path) -> Case`.
- Produces: `Case.timeout_s: float`, default `30.0`, containing a validated finite positive value.

- [ ] **Step 1: Write timeout parsing tests**

Add `test_case_timeout_defaults_to_thirty_seconds` and `test_case_timeout_accepts_positive_number`; assert the loaded cases contain `30.0` and the explicit numeric value respectively.

- [ ] **Step 2: Write invalid timeout tests**

Add one parametrized test covering YAML values `true`, `0`, `-1`, `.nan`, `.inf`, `-.inf`, `fast`, and `null`. Each load must raise `SpecError` containing `'timeout_s' must be a positive number`.

- [ ] **Step 3: Run the new tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_spec.py -k timeout -v`

Expected: failures because `Case` has no `timeout_s` and invalid values are accepted.

- [ ] **Step 4: Add and populate `Case.timeout_s`**

In `src/mcp_rig/spec.py`, add `timeout_s: float = 30.0` after `expect`. In `_parse_case`, reject booleans, non-numbers, non-finite values, and values `<= 0`, then construct the case with `timeout_s=float(timeout_s)`.

- [ ] **Step 5: Run spec tests and the full suite**

Run: `.venv/bin/python -m pytest tests/test_spec.py -v && .venv/bin/python -m pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/mcp_rig/spec.py tests/test_spec.py
git commit -m "feat: validate case timeouts"
```

### Task 2: Model and Report Case-Level Infrastructure Errors

**Files:**
- Modify: `src/mcp_rig/runner.py:1-53`
- Modify: `src/mcp_rig/report.py:1-23`
- Modify: `src/mcp_rig/cli.py:37-49`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_report.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Case.timeout_s`, `Probe.call(name, args=None, timeout_s=30.0) -> CallOutcome`, and `check(expect, outcome) -> list[str]`.
- Produces: `CaseStatus`, `ErrorCategory`, `InfrastructureError`, expanded `CaseResult`, expanded `SuiteResult`, and case-level timeout/transport classification.
- Preserves: `run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult` and `render_suite(title, result, color=False) -> str`.

- [ ] **Step 1: Write result-model and mixed-sequence runner tests**

Add tests that import these exact interfaces:

```python
class CaseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"

class ErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    SETUP = "setup"
    TRANSPORT = "transport"
    TEARDOWN = "teardown"

@dataclass(frozen=True)
class InfrastructureError:
    category: ErrorCategory
    exception_type: str
    message: str
```

Use a fake connection/probe for a three-case suite: the first case completes but fails an assertion, the second raises `ExceptionGroup("call", [RuntimeError("side"), TimeoutError()])`, and the third must never be called. Assert statuses `[FAILED, ERROR, SKIPPED]`, counts `(passed=0, failed=1, errors=1, skipped=1)`, timeout classification, `exception_type == "TimeoutError"`, the fallback message `operation timed out`, ordered call names, and the exact timeout passed for each attempted call.

- [ ] **Step 2: Write live timeout and cancellation-boundary tests**

Use the fixture server's existing `slow` tool with `timeout_s=0.01`; assert the active case becomes `ERROR`, its category is `TIMEOUT`, later cases are skipped, and elapsed time is non-negative. Add a fake probe that raises `KeyboardInterrupt` and assert it propagates rather than becoming a `CaseResult`.

- [ ] **Step 3: Run runner tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_runner.py -v`

Expected: import/signature failures because the status and error models do not exist and the runner does not pass `timeout_s`.

- [ ] **Step 4: Implement the runner result model**

Add these exact dataclasses:

```python
@dataclass(frozen=True)
class CaseResult:
    name: str
    status: CaseStatus
    elapsed_ms: float = 0.0
    failures: list[str] = field(default_factory=list)
    outcome: CallOutcome | None = None
    error: InfrastructureError | None = None
    skip_reason: str | None = None

@dataclass(frozen=True)
class SuiteResult:
    results: list[CaseResult]
    suite_error: InfrastructureError | None = None
```

Expose integer properties `passed`, `failed`, `errors`, and `skipped`; `errors` counts errored cases plus `suite_error`; `ok` requires every declared case to pass and no suite error.

- [ ] **Step 5: Implement case execution and exception normalization**

Measure elapsed time with `time.perf_counter`, call `probe.call(case.call, case.args, timeout_s=case.timeout_s)`, and classify the completed outcome with `check`. Implement `_normalize_error(exc: BaseException, fallback: ErrorCategory) -> InfrastructureError`: recursively select a `TimeoutError` leaf when `fallback is TRANSPORT`, otherwise select the first leaf and retain the fallback category. Use `operation timed out` when the selected timeout has an empty message. Catch `Exception`, not `BaseException`; after an error, append skipped results for the unstarted cases and stop the loop.

- [ ] **Step 6: Run runner tests and verify green**

Run: `.venv/bin/python -m pytest tests/test_runner.py -v`

Expected: all runner tests pass.

- [ ] **Step 7: Write terminal reporter tests for all case states**

Update the existing helper to construct the new result type. Add one exact-output test containing passed, failed, error, and skipped cases; assert marks `✓`, `✗`, `!`, `-`, the normalized error and skip reason, and the summary `1 passed, 1 failed, 1 error, 1 skipped`. Keep the color test and assert only status marks receive ANSI sequences.

- [ ] **Step 8: Run reporter tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_report.py -v`

Expected: failures because the reporter still assumes every result has an outcome and only two statuses exist.

- [ ] **Step 9: Render every case status**

Branch on `CaseStatus`, render elapsed milliseconds only for passed/failed/error cases, indent assertion or infrastructure details, show the skip reason without a duration, and pluralize summary labels as `error`/`errors` where appropriate.

- [ ] **Step 10: Write a CLI precedence test for a live timeout**

Add `test_run_timeout_exits_two_and_reports_skipped_cases` using `slow` followed by `echo`. Assert exit code 2, the `!` and `-` lines appear, and no traceback is printed.

- [ ] **Step 11: Run the timeout CLI test and verify red**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_run_timeout_exits_two_and_reports_skipped_cases -v`

Expected: FAIL because the CLI maps every non-OK result to exit code 1.

- [ ] **Step 12: Implement CLI result precedence**

Return 2 when `result.errors > 0`, 1 when `result.failed > 0`, otherwise 0.

- [ ] **Step 13: Run task tests and full verification**

Run: `.venv/bin/python -m pytest tests/test_runner.py tests/test_report.py tests/test_cli.py -v && .venv/bin/python -m pytest && .venv/bin/ruff check src tests`

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 14: Commit**

```bash
git add src/mcp_rig/runner.py src/mcp_rig/report.py src/mcp_rig/cli.py tests/test_runner.py tests/test_report.py tests/test_cli.py
git commit -m "feat: report case infrastructure failures"
```

### Task 3: Capture Suite Setup and Teardown Errors

**Files:**
- Modify: `src/mcp_rig/runner.py`
- Modify: `src/mcp_rig/report.py`
- Modify: `src/mcp_rig/cli.py`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_report.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2's result model, `_normalize_error(exc: BaseException, fallback: ErrorCategory) -> InfrastructureError`, and ordered case execution.
- Produces: structured `SETUP` and `TEARDOWN` suite errors while retaining declared or completed case results.
- Preserves: case-level errors and exit-code precedence from Task 2.

- [ ] **Step 1: Write lifecycle tests across runner, reporter, and CLI**

Change the existing missing-executable runner test to expect a returned `SuiteResult`: `suite_error.category is SETUP`, every declared case is `SKIPPED`, `errors == 1`, and `ok is False`. Assert the skip reason says the suite could not start.
In the same lifecycle test slice, monkeypatch `connect` with an async context manager that yields a working fake probe and raises `RuntimeError("close failed")` after the yield. Assert completed case statuses remain unchanged, `suite_error.category is TEARDOWN`, its message is `close failed`, and the error count includes exactly one suite error. Add reporter assertions for separate `! suite setup: ...` and `! suite teardown: ...` lines and summaries that include the suite error. Update the public missing-executable CLI test to require exit 2, structured setup/skipped output, and no traceback.

- [ ] **Step 2: Run lifecycle tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_runner.py tests/test_report.py tests/test_cli.py -k "setup or teardown or infrastructure_failure or unstartable" -v`

Expected: failures because setup/teardown exceptions still propagate.

- [ ] **Step 3: Capture connection lifecycle failures in `run_suite`**

Track whether the connection yielded successfully. Normalize a pre-yield exception as `SETUP`, create skipped results for every declared case, and return them with `suite_error`. Normalize an exception raised while leaving the context as `TEARDOWN`, retaining results already produced. Continue to let `BaseException` subclasses propagate.

- [ ] **Step 4: Run runner lifecycle tests and verify green**

Run: `.venv/bin/python -m pytest tests/test_runner.py -k "setup or teardown or infrastructure_failure" -v`

Expected: all selected runner tests pass.

- [ ] **Step 5: Render suite-level lifecycle errors**

Extend `render_suite` with a separate `! suite <category>: <exception_type>: <message>` line when `suite_error` exists. Do not create a second declared-case line; the summary's error count already includes the suite error.

- [ ] **Step 6: Run reporter and CLI lifecycle tests and verify green**

Run: `.venv/bin/python -m pytest tests/test_report.py tests/test_cli.py -k "setup or teardown or unstartable" -v`

Expected: all selected reporter and CLI tests pass.

- [ ] **Step 7: Run task tests and full verification**

Run: `.venv/bin/python -m pytest tests/test_runner.py tests/test_report.py tests/test_cli.py -v && .venv/bin/python -m pytest && .venv/bin/ruff check src tests`

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 8: Commit**

```bash
git add src/mcp_rig/runner.py src/mcp_rig/report.py src/mcp_rig/cli.py tests/test_runner.py tests/test_report.py tests/test_cli.py
git commit -m "feat: capture suite lifecycle failures"
```

### Task 4: Serialize Structured Results as JUnit XML

**Files:**
- Create: `src/mcp_rig/junit.py`
- Create: `tests/test_junit.py`

**Interfaces:**
- Consumes: Task 3's `CaseStatus`, `InfrastructureError`, `CaseResult`, and `SuiteResult`.
- Produces: `write_junit(path: str | Path, suite_name: str, result: SuiteResult) -> None`.

- [ ] **Step 1: Write a complete JUnit structure test**

Build a `SuiteResult` with one passed case, one two-message assertion failure, one transport error, one skipped case, and a teardown suite error. Parse the output with ElementTree and assert:

- `<testsuites>` contains one `<testsuite>`;
- suite attributes are `tests="5"`, `failures="1"`, `errors="2"`, and `skipped="1"`;
- declared testcase order is preserved and `[suite teardown]` is last;
- durations convert from milliseconds to seconds with three decimals;
- failed, errored, skipped, and synthetic cases use `<failure>`, `<error>`, `<skipped>`, and `<error>` respectively; and
- the failure body contains both assertion messages.

- [ ] **Step 2: Write XML escaping and write-failure tests**

Use suite/case/messages containing `&`, `<`, `>`, and quotes; parse the file and assert values round-trip exactly. Pass a path below a missing parent and assert `OSError` propagates.

- [ ] **Step 3: Run JUnit tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_junit.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'mcp_rig.junit'`.

- [ ] **Step 4: Implement `write_junit`**

Use `xml.etree.ElementTree` only. Emit a `<testsuites>` root, one `<testsuite>` with name/count/time attributes, one testcase per declared result, and a final synthetic testcase when `suite_error` exists. Set testcase `classname` to the suite name and format every time as seconds with three decimals. Let ElementTree escape all content and let file errors propagate.

- [ ] **Step 5: Run JUnit and full verification**

Run: `.venv/bin/python -m pytest tests/test_junit.py -v && .venv/bin/python -m pytest && .venv/bin/ruff check src tests`

Expected: all tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/mcp_rig/junit.py tests/test_junit.py
git commit -m "feat: write structured JUnit reports"
```

### Task 5: Expose JUnit and Document the Completed Run Workflow

**Files:**
- Modify: `src/mcp_rig/cli.py:19-49`
- Modify: `tests/test_cli.py`
- Modify: `README.md:15-38`
- Modify: `examples/fixture.yaml:1-36`

**Interfaces:**
- Consumes: `write_junit(path, suite_name, result)`, `render_suite`, and Task 3's result counts.
- Produces: public `mcp-rig run SUITE --junit PATH` behavior and documented timeout/JUnit/exit-code contract.

- [ ] **Step 1: Write successful and assertion-failure JUnit CLI tests**

For a passing suite, assert exit 0, a parseable report, and zero failures/errors. For a failing suite, assert exit 1 and a report containing the expected `<failure>` while terminal output remains present.

- [ ] **Step 2: Write infrastructure JUnit CLI tests**

For a timeout followed by an unstarted case, assert exit 2 and JUnit `<error>` plus `<skipped>`. For an unstartable server, assert exit 2 and a report containing `[suite setup]` plus skipped declared cases.

- [ ] **Step 3: Write configuration and output-path boundary tests**

Assert invalid YAML/configuration returns 2 and does not create a requested JUnit file. Assert a valid run with a JUnit path below a missing directory prints the terminal result, returns 2, emits a concise `could not write JUnit report` message to stderr, and prints no traceback.

- [ ] **Step 4: Run the new CLI tests and verify red**

Run: `.venv/bin/python -m pytest tests/test_cli.py -k junit -v`

Expected: parser errors because `--junit` is not defined.

- [ ] **Step 5: Add the flag and JUnit orchestration**

Add `--junit PATH` to the `run` parser. After execution and terminal rendering, call `write_junit(args.junit, args.suite, result)` when requested. Catch `OSError` from report writing, print `error: <path>: could not write JUnit report: <type>: <message>`, and return 2. Do not invoke the writer when `load_suite` raises `SpecError`.

- [ ] **Step 6: Document timeout, statuses, JUnit, and exit codes**

Update `README.md` with one run example using `--junit`, the `timeout_s` default/validation contract, passed/failed/error/skipped meaning, and exit codes 0/1/2. Remove timeout and JUnit from the later-increments sentence. Add `timeout_s: 5` to the advanced case in `examples/fixture.yaml` and update its opening command comment to show the optional JUnit flag.

- [ ] **Step 7: Run complete verification**

Run:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
.venv/bin/pip check
.venv/bin/mcp-rig run examples/fixture.yaml --junit /tmp/mcp-rig-results.xml
.venv/bin/python -c "import xml.etree.ElementTree as ET; ET.parse('/tmp/mcp-rig-results.xml')"
```

Expected: every command exits 0; all tests pass; Ruff and pip report no problems; the example reports `3 passed, 0 failed, 0 errors, 0 skipped`; ElementTree parses the report.

- [ ] **Step 8: Commit**

```bash
git add src/mcp_rig/cli.py tests/test_cli.py README.md examples/fixture.yaml
git commit -m "feat: expose JUnit run reporting"
```

## Completion Review

After Task 5, compare the complete branch diff with `docs/superpowers/specs/2026-09-26-run-reliability-reporting-design.md` and confirm:

- timeout values are validated before server startup and passed to every attempted call;
- tool-level MCP errors remain assertion-visible call outcomes;
- case and suite infrastructure failures are structurally distinct from assertion failures;
- no call occurs after a timeout or transport error, and later cases remain ordered as skipped;
- setup and teardown errors retain declared or completed results;
- terminal and JUnit counts agree for all statuses;
- JUnit is attempted for completed/incomplete runtime results but not invalid configuration;
- exit code 2 overrides exit code 1 when both assertion and infrastructure failures exist;
- existing usage remains compatible without `timeout_s` or `--junit`; and
- multi-suite, `check`, remote transport, retry/restart, CI, and release work were not added.

Run the full verification block once more after review. Stop after the review; do not begin `check` or release work without explicit approval.
