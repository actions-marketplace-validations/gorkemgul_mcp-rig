# MCP Rig Stdio Suite Execution Design

## Purpose

This increment turns MCP Rig's tested stdio client foundation into its first
user-visible workflow. A user describes a local MCP server and tool cases in a
YAML file, then runs the complete suite with:

```bash
mcp-rig run path/to/suite.yaml
```

The command starts one local stdio server, executes cases sequentially, checks
the minimal `is_error` and `contains` expectations, prints a terminal report,
and returns an automation-friendly exit code.

## Scope

This increment includes:

- YAML suite parsing and validation.
- Structured suite and case models owned by MCP Rig.
- `is_error` and `contains` assertions.
- Sequential execution against one stdio server process per suite.
- Human-readable terminal reporting.
- The `mcp-rig run` command and `--server-logs` diagnostic flag.
- Exit codes `0`, `1`, and `2` for success, assertion failure, and
  configuration/infrastructure failure.

This increment does not include:

- `not_contains`, regular expressions, latency assertions, JSON path, or JSON
  Schema assertions.
- Per-case timeout handling beyond the client layer's existing default.
- JUnit XML.
- The `check` command or tool-definition linting.
- HTTP, SSE, resources, prompts, snapshots, plugins, or parallel execution.
- PyPI publication or release automation.

## User Contract

### Canonical YAML

```yaml
server:
  command: python
  args: [server.py]
  env:
    MODE: test
  cwd: .

tests:
  - name: add returns five
    call: add
    args:
      a: 2
      b: 3
    expect:
      is_error: false
      contains: "5"
```

The server may also use a shell-like shorthand:

```yaml
server: "python server.py"
```

### Validation Rules

- The document root must be a mapping.
- `server` and `tests` are required.
- `server` must be either a non-empty command string or a mapping with a
  non-empty string `command`.
- Server `args` must be a list of strings when present.
- Server `env` must be a string-to-string mapping when present.
- Server `cwd` must be a string when present.
- `tests` must be a non-empty list.
- Every case must be a mapping with non-empty string `name` and `call` fields.
- Case `args` defaults to `{}` and must be a mapping when present.
- Case `expect` defaults to `{}` and must be a mapping when present.
- The only recognized expectation keys are `is_error` and `contains`.
- Unknown expectation keys are configuration errors, not ignored input.
- `is_error` must be a boolean when present and defaults to `false` during
  assertion evaluation.
- `contains` may be a string or a non-empty list of strings.
- Relative `cwd` values are resolved from the suite file's directory.

The complete suite is parsed and validated before any subprocess starts.
Malformed YAML and invalid structures raise an MCP Rig-owned `SpecError` with
a concise, user-facing message.

## Architecture

The workflow adds five focused modules on top of the existing stdio client:

```text
YAML file
   |
   v
spec.py -> Suite / Case
   |
   v
runner.py -> one connected Probe, sequential calls
   |
   +--> assertions.py -> failure messages
   |
   v
SuiteResult / CaseResult
   |
   v
report.py -> terminal text
   |
   v
cli.py -> output + exit code
```

### `spec.py`

Owns YAML parsing, validation, defaults, and path resolution. It returns
MCP Rig-owned immutable configuration models:

- `Case(name, call, args, expect)`
- `Suite(path, server, cases)`
- `SpecError`

The parser does not start a server or depend on terminal behavior.

### `assertions.py`

Provides a pure function that compares a `CallOutcome` with one case's
expectations and returns a list of readable failure strings.

Rules:

- Missing `is_error` means `false`.
- `is_error` compares the expected and actual error flags.
- Every `contains` string must occur in `CallOutcome.text`.
- A tool-level error is still an ordinary outcome and can pass when
  `is_error: true` is expected.

### `runner.py`

Owns suite orchestration and result models:

- `CaseResult(name, passed, failures, outcome)`
- `SuiteResult(results)` with derived passed and failed counts.
- `run_suite(suite, show_server_logs=False)`

`run_suite` opens one connection with the Phase 1 `connect()` function, runs
cases in YAML order, evaluates each outcome, and continues after assertion
failures. It does not format terminal output or select process exit codes.

Subprocess startup failure, unexpected connection loss, and other client
exceptions remain infrastructure failures and propagate to the CLI. They are
not converted into assertion mismatches.

### `report.py`

Transforms a `SuiteResult` into deterministic terminal text. It renders one
line per case, indented failure details, and a final passed/failed summary.

Color is enabled only when the output stream is interactive. Piped and CI
output remains plain text. Report functions remain independent from execution
and filesystem access.

### `cli.py`

Uses `argparse` and exposes:

```bash
mcp-rig run SUITE
mcp-rig run SUITE --server-logs
```

The CLI remains thin: parse arguments, load the suite, run it, render the
result, handle expected configuration/infrastructure failures, and select an
exit code.

`pyproject.toml` registers `mcp-rig = "mcp_rig.cli:main"` as the console
script.

## Execution and Error Semantics

The command uses these exit codes:

- `0`: the suite was valid, executed, and every case passed.
- `1`: the suite was valid and executed, but at least one case failed its
  expectations.
- `2`: command usage, YAML parsing, configuration, server startup, connection,
  or another infrastructure failure prevented a valid completed run.

Assertion failure does not stop later cases. Infrastructure failure aborts the
suite because the remaining calls cannot be trusted to execute against the
intended server session.

Server stderr stays suppressed by default through the Phase 1 client. The
`--server-logs` flag opts into forwarding it for diagnosis.

Expected user output resembles:

```text
MCP Rig — examples/basic.yaml

✓ add returns five
✗ greeting contains name
    contains: 'Ada' not found in 'Hello'

1 passed, 1 failed
```

Infrastructure and configuration failures are concise and do not include a
traceback during normal CLI use.

## Testing Strategy

Development remains test-first.

- `tests/test_spec.py` covers canonical and shorthand servers, defaults,
  relative `cwd`, malformed YAML, missing fields, invalid field types, and
  unknown expectation keys.
- `tests/test_assertions.py` covers default success, explicit tool-error
  expectations, single and multiple `contains` values, and stable readable
  failure messages.
- `tests/test_runner.py` uses the real stdio fixture to prove one-session,
  ordered execution and continuation after an assertion failure.
- `tests/test_report.py` checks deterministic success, failure, detail, and
  summary output without requiring a server.
- `tests/test_cli.py` invokes the public CLI boundary with real YAML suites and
  verifies exit codes `0`, `1`, and `2`, output, and `--server-logs` routing.
- All existing Phase 1 integration tests continue to pass.

The completion gate is the full pytest suite plus Ruff across `src` and
`tests`. No release or publish action is part of this increment.

## Success Criteria

This increment is complete when:

- A user can install the project in editable mode and run
  `mcp-rig run path/to/suite.yaml`.
- A valid suite starts one stdio server and executes every case in order.
- `is_error` and `contains` produce correct pass/fail results.
- Terminal output identifies every case and summarizes the run.
- Exit codes distinguish success, assertion failure, and invalid execution.
- Invalid suites are rejected before the server starts.
- The full pytest and Ruff gates pass.
