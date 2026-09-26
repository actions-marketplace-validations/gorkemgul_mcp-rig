# MCP Rig Run Reliability and Reporting Design

## Purpose

Complete the reliability boundary of the local `mcp-rig run` workflow. A
suite must distinguish assertion failures from failures that prevented MCP Rig
from executing a case reliably, preserve that distinction in terminal and
JUnit output, and apply a validated timeout to every tool call.

This increment completes the remaining `run` work from the approved MCP Rig
0.1 design. It does not add protocol checks, additional transports, multi-file
execution, release automation, or PyPI publication.

## Scope

This increment adds:

- a positive, finite `timeout_s` value on each YAML case, defaulting to 30
  seconds;
- explicit passed, failed, infrastructure-error, and skipped case states;
- deterministic behavior when a timeout, connection loss, server exit, setup
  failure, or teardown failure interrupts a suite;
- terminal output that reports all four case states separately;
- `mcp-rig run SUITE --junit PATH`;
- JUnit XML that represents assertion failures, infrastructure errors, and
  skipped cases with their native JUnit elements;
- stable exit-code behavior for successful, failed, and incomplete runs; and
- documentation and examples for timeouts and JUnit output.

The following remain out of scope:

- multiple suite paths in one command;
- retries or server restarts after an infrastructure failure;
- continuing the suite after a timeout or broken transport;
- protocol checks and tool-description linting;
- HTTP, SSE, or other remote transports;
- CI/release automation and PyPI publication.

## User Contract

### Per-Case Timeout

Every test case may set `timeout_s`:

```yaml
tests:
  - name: responds promptly
    call: slow
    args: {seconds: 0.1}
    timeout_s: 1.0
    expect:
      contains: done
```

An omitted value means 30 seconds. The value must be an integer or float that
is finite and greater than zero. Booleans are rejected even though Python
treats them as integers. Invalid timeout configuration is a `SpecError` and is
reported before the server starts.

The validated value is passed unchanged to `Probe.call`. A tool call that does
not complete within the limit becomes an infrastructure error, not an
assertion failure.

### JUnit Output

`mcp-rig run SUITE --junit PATH` writes one XML document for the requested
suite. The parent directory must already exist. The report is written for
passing suites, assertion failures, case-level infrastructure errors, and
suite setup or teardown errors.

An XML write failure is reported as an infrastructure/usage failure and causes
exit code 2. MCP Rig does not create missing report directories.

## Result Model

### Case Status

`runner.py` owns a string-backed `CaseStatus` enum with these values:

- `passed`: the call completed and all expectations matched;
- `failed`: the call completed but one or more expectations did not match;
- `error`: MCP Rig could not complete the call reliably;
- `skipped`: the case was not started because an earlier infrastructure error
  made the shared session unreliable.

`CaseResult` contains:

- the case name;
- its `CaseStatus`;
- assertion failure messages;
- an optional `CallOutcome`;
- an optional normalized infrastructure error; and
- an optional skip reason; and
- elapsed milliseconds measured by the runner.

Only failed results contain assertion failures. Passed and failed results
contain a call outcome. Error and skipped results have no outcome. Error
results contain an infrastructure error; skipped results contain a short
reason that identifies the earlier interruption.

`SuiteResult` contains ordered case results plus an optional suite-level
infrastructure error. It exposes counts for passed, failed, errored, and
skipped cases. Its total `errors` count is the number of errored cases plus one
when a suite-level setup or teardown error exists. `ok` is true only when
every declared case passed and there is no suite-level error.

### Infrastructure Error

The runner normalizes an exception into an immutable value containing:

- a stable category: `timeout`, `setup`, `transport`, or `teardown`;
- the exception type; and
- a concise message with nested `BaseExceptionGroup` wrappers removed.

This value is safe for reporters and prevents terminal and JUnit formatting
from depending on SDK-specific exception objects. Normalization does not turn
MCP tool errors into infrastructure errors: a server-returned tool error
remains a normal `CallOutcome(is_error=True)` and can be asserted with
`is_error`.

## Execution Semantics

One server process and one initialized client session remain shared by the
whole suite. Cases run sequentially in YAML order.

For each case, the runner records elapsed time around `Probe.call` and passes
the case's `timeout_s`. A completed call goes through the existing assertion
engine and becomes passed or failed.

If `Probe.call` raises a timeout or another infrastructure exception:

1. the active case becomes `error`;
2. all later declared cases become `skipped` in their original order;
3. no later tool call is attempted; and
4. the connection context is allowed to close normally.

Continuing after a timeout or transport error is intentionally disallowed.
The timed-out request may still be running in the server, and a broken MCP
session cannot be assumed to remain synchronized. Automatic server restart is
also excluded because it would silently discard server state.

If the server cannot start or the session cannot initialize, no declared case
is executed. All declared cases become skipped and the `SuiteResult` receives
a `setup` error. If closing the connection fails after execution, completed
case results are retained and the suite receives a `teardown` error. A
teardown error does not rewrite already completed case statuses.

Cancellation requested by the host process is not converted into a test
result. `KeyboardInterrupt`, `SystemExit`, and cancellation exceptions continue
to propagate.

## Terminal Reporting

The terminal report uses one line per declared case:

- `✓` for passed;
- `✗` for assertion failure;
- `!` for an infrastructure error; and
- `-` for skipped.

Passed and failed cases show elapsed milliseconds. Error cases show the
elapsed time followed by the normalized error. Skipped cases show their skip
reason without a fabricated duration. Assertion messages remain indented
below failed cases.

A suite-level setup or teardown error is rendered as a separate `! suite`
line. The final summary always reports `passed`, `failed`, `errors`, and
`skipped`. Existing color behavior remains limited to status marks; errors use
red and skipped cases remain uncolored.

## JUnit XML Contract

`junit.py` is a pure formatting module built with
`xml.etree.ElementTree`. Its public function is:

```python
write_junit(path: str | Path, suite_name: str, result: SuiteResult) -> None
```

The document has a `<testsuites>` root and one `<testsuite>` child. The suite
attributes include `name`, `tests`, `failures`, `errors`, `skipped`, and
aggregate `time` in seconds.

Each declared YAML case produces one `<testcase>` in source order:

- passed cases have no child status element;
- failed cases contain `<failure>`, with the first assertion message in the
  `message` attribute and every assertion message in the body;
- errored cases contain `<error>`, with the normalized category/type in the
  attributes and the concise error text in the body; and
- skipped cases contain `<skipped message="...">`.

Case time is formatted in seconds with three decimal places. XML escaping is
delegated to ElementTree.

A setup or teardown error adds one synthetic testcase named `[suite setup]`
or `[suite teardown]`, containing `<error>`. The synthetic testcase is counted
in the suite's `tests` and `errors` attributes. Declared cases remain present,
so setup failures show the suite error alongside the cases that were skipped.

The writer creates the target file directly with an XML declaration. It does
not create parent directories or suppress `OSError`.

## CLI and Exit Codes

The existing `run` parser gains:

```text
--junit PATH  also write a JUnit XML report
```

The command loads one suite, executes it, prints the terminal report, and then
writes JUnit when requested. Report writing happens even when the suite has
assertion or infrastructure results. Configuration errors occur before
execution and therefore do not produce JUnit.

Exit codes remain:

- `0`: every case passed and JUnit writing, if requested, succeeded;
- `1`: execution completed without infrastructure errors, but at least one
  assertion failed;
- `2`: invalid configuration, any infrastructure error, or failure to write
  the requested JUnit file.

Infrastructure status takes precedence over assertion status. A suite that
contains both an earlier assertion failure and a later infrastructure error
exits 2.

The CLI continues to omit tracebacks for expected configuration and
infrastructure failures. It reports a concise error for JUnit write failures;
case and suite infrastructure details are already present in the terminal
report.

## Architecture and File Changes

### `src/mcp_rig/spec.py`

Add `timeout_s: float = 30.0` to `Case` and validate YAML timeout values before
constructing a case. No timeout logic belongs in the parser.

### `src/mcp_rig/runner.py`

Own `CaseStatus`, the normalized infrastructure-error value, the expanded
`CaseResult` and `SuiteResult`, exception normalization, execution control,
elapsed-time measurement, and conversion of runtime failures into structured
results.

### `src/mcp_rig/client.py`

Keep the existing `Probe.call(..., timeout_s=...)` boundary. No SDK exceptions
are swallowed here; the runner owns policy and result classification.

### `src/mcp_rig/report.py`

Render the structured result without inspecting exceptions or inferring a
status from missing values.

### `src/mcp_rig/junit.py`

Convert a `SuiteResult` into deterministic JUnit XML. It performs no execution
or exception classification.

### `src/mcp_rig/cli.py`

Add the JUnit flag, invoke the writer, and choose an exit code from the
structured result. Configuration failures and report-write failures remain CLI
boundary concerns.

## Testing Strategy

Development remains test-first. Tests cover:

- default, explicit, boolean, zero, negative, non-numeric, infinite, and NaN
  timeout values in `spec.py`;
- propagation of the validated timeout to `Probe.call`;
- passed, failed, errored, and skipped result construction;
- a real fixture-server timeout;
- fixture-server termination during a case;
- setup failure before the first case;
- retention of completed cases when teardown fails;
- the rule that no later tool call occurs after an infrastructure error;
- terminal formatting and counts for every status;
- JUnit counts, time conversion, ordering, XML escaping, failure bodies,
  errors, skipped cases, and synthetic setup/teardown cases;
- CLI exit codes 0, 1, and 2;
- `--junit` output for success, assertion failure, timeout, and setup failure;
  and
- a concise error when the JUnit path cannot be written.

Existing assertion, client, suite execution, and public CLI tests remain
green. The completion gate is the full pytest suite, Ruff across `src` and
`tests`, `pip check`, and execution of the installed example suite with a
JUnit report that can be parsed by ElementTree.

## Success Criteria

This increment is complete when:

- every case has a validated timeout and the runner applies it;
- assertion failures and infrastructure errors cannot be confused in the
  result model or either reporter;
- a timeout or broken session aborts further calls and records later cases as
  skipped;
- setup and teardown errors retain enough structure for terminal and JUnit
  reporting;
- JUnit accurately counts and represents passed, failed, errored, and skipped
  results;
- CLI exit codes follow the documented precedence;
- existing workflows remain compatible when `timeout_s` and `--junit` are
  omitted; and
- no `check`, remote transport, multi-suite, restart/retry, CI, or release
  functionality is introduced.
