# Batch Suite Execution Design

## Goal

Allow one `mcp-rig run` invocation to execute one or more suite files and
directories while preserving the existing single-suite command, deterministic
results, exit-code contract, and CI-friendly reporting.

This is the first pre-0.1 feature increment. Test filtering, tags, snapshots,
and the PyPI release remain separate later increments.

## User Interface

The `run` command accepts one or more targets:

```console
mcp-rig run tests/mcp/smoke.yaml
mcp-rig run tests/mcp/smoke.yaml tests/mcp/regression.yaml
mcp-rig run tests/mcp/
mcp-rig run tests/mcp/ examples/fixture.yaml --junit results.xml
```

Each target is either:

- a `.yaml` or `.yml` suite file; or
- a directory searched recursively for `.yaml` and `.yml` files.

Shell-expanded globs work naturally because each expanded path is another
target. MCP Rig does not implement an internal glob language in this increment.

Targets that resolve to the same absolute file are deduplicated. Discovered
suite paths are sorted by normalized absolute path before execution, so command
line ordering, directory traversal order, and operating-system filesystem order
cannot change the run order.

The existing successful single-suite command remains valid without changing
its terminal output:

```console
mcp-rig run examples/fixture.yaml
```

## Target Discovery and Validation

A focused discovery function converts raw CLI targets into an ordered list of
suite paths plus target-level configuration errors. It performs filesystem
discovery only; suite parsing remains owned by `load_suite`.

Discovery applies these rules:

1. A supported file is included directly.
2. A directory is searched recursively for supported files.
3. A missing path is a configuration error.
4. A regular file without a `.yaml` or `.yml` suffix is a configuration error.
5. A directory containing no supported suite files is a configuration error.
6. Permission and traversal failures are configuration errors tied to the
   original target.

Valid suites discovered from other targets still run when one target produces a
discovery error. If discovery produces no suite files, MCP Rig reports all
target errors and exits with code `2` without starting a server.

## Execution Model

Suites run sequentially in deterministic path order. Parallel server execution
is deliberately excluded from this increment because it would make terminal
output, resource use, and failure diagnosis less predictable.

Each suite keeps its existing lifecycle:

1. parse its YAML configuration;
2. start its configured stdio server;
3. execute cases in declaration order through one shared session;
4. stop that server; and
5. retain its structured result or suite-level error.

A parse, startup, connection, or teardown failure is isolated to the current
suite. MCP Rig records the failure and continues with the next discovered
suite. An error inside one suite may still skip later cases in that suite under
the existing runner rules, but it never skips a different suite.

The batch runner returns one structured record per suite and retains
target-level discovery errors separately. Reporting and exit decisions consume
this aggregate instead of reconstructing state from exceptions or formatted
text.

## Terminal Reporting

For one suite, terminal output remains byte-for-byte compatible with the
current renderer.

For multiple suites, MCP Rig renders the existing per-suite report for each
suite, separated by one blank line, followed by an aggregate summary such as:

```text
Suites: 2 passed, 1 failed, 1 error
Cases: 8 passed, 2 failed, 1 error, 1 skipped
```

A suite is:

- `passed` when all its cases pass;
- `failed` when it has assertion failures but no infrastructure error; or
- `error` when discovery, parsing, startup, execution infrastructure, or
  teardown prevents a reliable result.

Target-level discovery errors are printed with their target path before suite
results. Server stderr remains hidden unless `--server-logs` is supplied; that
flag applies to every executed suite.

## JUnit Reporting

The JUnit writer emits one `<testsuite>` child per discovered suite beneath a
single `<testsuites>` root. Existing case mapping remains unchanged:

- assertion failures become `<failure>`;
- infrastructure errors become `<error>`; and
- cases not started after a suite infrastructure error become `<skipped>`.

Discovery and parse errors have no real case, so each becomes one synthetic
testcase in the affected suite or target testsuite. Synthetic cases use a
stable name and contain the normalized error message.

This intentionally improves one existing edge case: when `--junit` is present,
a single invalid or missing suite now produces a synthetic error testcase
instead of suppressing the report entirely.

Aggregate count and duration attributes on `<testsuites>` equal the sums of its
children. Output ordering follows deterministic suite ordering. Invalid JUnit
destinations retain the current exit-code precedence and never replace an input
suite because the existing input/output path collision guard applies to every
discovered suite file.

If the JUnit destination resolves to any discovered suite file, MCP Rig exits
with code `2` before suite parsing or execution and does not write a report.

## Exit Codes

The public exit-code contract remains:

- `0`: discovery succeeded and every executed case passed;
- `1`: at least one assertion failed and there were no configuration or
  infrastructure errors; and
- `2`: any target, suite configuration, server, connection, teardown, or report
  writing error occurred.

Exit code `2` takes precedence over `1`, even though all discoverable suites are
still executed before the process exits.

## Component Changes

The implementation should keep responsibilities narrow:

- `discovery.py` owns target traversal, validation, deduplication, and ordering.
- `batch.py` owns aggregate models and sequential suite orchestration. It calls
  `load_suite` and the existing `run_suite` at suite boundaries instead of
  duplicating parsing or case execution.
- `report.py` gains batch terminal rendering and aggregate counts while
  preserving `render_suite` for the compatibility path.
- `junit.py` gains multi-suite document generation while reusing the current
  case-to-XML mapping.
- `cli.py` changes the `suite` positional argument to `targets` with `nargs="+"`
  and coordinates discovery, execution, reporting, and exit precedence.

## Error Handling

User-facing errors identify the smallest useful source: the original target,
the resolved suite path, and the case when applicable. Raw exception groups and
tracebacks remain hidden under normal CLI use.

The batch layer catches errors only at suite boundaries. It must not convert
assertion failures into infrastructure errors or suppress process cancellation.
Existing exception normalization remains the source of suite-level error text.

## Testing Strategy

Development remains test-first. Tests cover:

- mixed files and recursive directories;
- `.yaml` and `.yml` discovery;
- deterministic ordering and duplicate removal;
- missing, unsupported, empty, and unreadable targets;
- continuing after parse and infrastructure failures;
- aggregate suite/case counts and exit-code precedence;
- multi-suite JUnit structure, counts, order, and synthetic errors;
- compatibility of the existing one-file command and terminal output;
- `--server-logs` behavior across multiple suites; and
- end-to-end CLI execution with multiple deterministic fixture servers.

The full Python test matrix, Ruff, package build, Twine validation, and installed
wheel smoke test remain required before merge.

## Documentation

The README will show single-file, multiple-file, and recursive-directory
examples. It will explain deterministic ordering, continuation after suite
errors, aggregate exit codes, and combined JUnit output.

## Non-Goals

This increment does not add:

- internal glob expansion;
- parallel suite execution;
- fail-fast mode;
- case-name filtering;
- tags;
- snapshot assertions;
- remote MCP transports; or
- changes to resources, prompts, or other MCP surfaces.
