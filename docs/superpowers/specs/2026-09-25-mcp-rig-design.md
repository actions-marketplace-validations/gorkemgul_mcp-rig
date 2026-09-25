# MCP Rig 0.1 Design

## Purpose

MCP Rig is a local-first command-line tool for deterministic, CI-friendly testing of Model Context Protocol servers. It launches an MCP server as a local subprocess over stdio, behaves as a real MCP client, calls tools, and checks the results against declarative YAML expectations.

The first milestone is a useful local tool. PyPI packaging follows after the local workflows have been validated, without restructuring the core application.

## Product Identity

- Product name: MCP Rig
- GitHub repository: `git@github.com:gorkemgul/mcp-rig.git`
- PyPI distribution: `mcp-rig`
- Python package: `mcp_rig`
- CLI command: `mcp-rig`

The earlier `mcptest` name and examples in the source plan will be renamed during implementation.

## Scope

Version 0.1 supports:

- MCP servers launched as local subprocesses over stdio.
- MCP tools: discovery, invocation, result assertions, and definition linting.
- Declarative YAML test suites.
- Human-readable terminal reports and JUnit XML.
- Protocol and tool-definition checks that require no test suite.
- Exit codes suitable for local scripting and CI.

Version 0.1 does not support:

- Streamable HTTP, SSE, or remote URL targets.
- MCP resources or prompts.
- Snapshot testing.
- A pytest plugin.
- LLM-driven evaluations.
- Parallel test execution.
- A plugin system or general-purpose transport framework.

The boundaries between the client and runner must remain clean enough to add an HTTP client later without changing suite parsing, assertions, reporting, or CLI result semantics.

## Delivery Phases

### Phase 1: Stdio Foundation

Create the package skeleton, a controlled fixture MCP server, and the stdio client layer. The client owns subprocess startup, MCP session initialization, tool discovery, tool invocation, latency measurement, and clean shutdown.

Completion criteria:

- MCP Rig can start the fixture server.
- It can list the fixture server's tools.
- It can invoke a tool successfully and capture both successful and error results.
- Connection behavior is covered by integration tests using a real stdio MCP session.

### Phase 2: Usable Local `run` MVP

Add YAML parsing, `is_error` and `contains` assertions, suite execution, terminal reporting, and the `mcp-rig run` command. This phase must produce a user-visible vertical slice rather than only isolated library modules.

Completion criteria:

- A user can describe a local server and tool cases in YAML.
- `mcp-rig run path/to/suite.yaml` starts the server and runs every case.
- Passing and failing cases are readable in the terminal.
- Exit codes distinguish success, test failure, and usage/configuration errors.

### Phase 3: Complete the `run` Workflow

Add `not_contains`, `matches`, `max_latency_ms`, `json_path`, and `schema`; then complete timeout and infrastructure-error behavior, JUnit XML, and CLI robustness.

Completion criteria:

- All documented expectation keys are implemented and tested.
- Timeout, malformed suite, unknown tool, tool error, server failure, and unknown expectation keys have explicit behavior.
- JUnit output represents passed, failed, and infrastructure-error cases correctly.
- The full test and lint suite is clean.

### Phase 4: `check` and Tool Linting

Add protocol behavior checks and deterministic quality checks for advertised tool definitions. Both reuse the stdio client from Phase 1.

Completion criteria:

- `mcp-rig check "python server.py"` verifies the safe default protocol checks.
- `--probe-invalid-args` explicitly enables potentially side-effecting invalid-argument probes.
- `--strict` turns lint warnings into a failing exit code.
- The server remains usable after deliberately invalid protocol calls.

### Phase 5: Release Readiness and PyPI

Validate MCP Rig outside its own fixture, finalize documentation and CI, build distribution artifacts, and verify installation in a clean environment.

Completion criteria:

- At least one independent example stdio MCP server passes the intended smoke workflow.
- The supported Python matrix passes tests and linting in CI.
- The wheel installs in a clean virtual environment.
- `mcp-rig --help`, `mcp-rig run`, and `mcp-rig check` work from the installed wheel.
- The package is ready for a deliberate PyPI 0.1 release.

Each phase is a review gate. Completing one phase does not automatically authorize starting the next.

## Technical Constraints

- Python 3.11 or newer.
- MCP Python SDK 2.x, verified against its current public API during Phase 1.
- `argparse` for the CLI.
- PyYAML for suite parsing and `jsonschema` for schema assertions and linting.
- Hatchling for packaging; pytest with AnyIO for tests; Ruff for linting.
- No additional runtime dependencies without a design review.

## Architecture

### `client.py`

Owns the stdio MCP lifecycle. It converts server configuration into a subprocess, initializes an MCP client session, lists tools, invokes tools, measures latency, and returns normalized outcomes.

The public boundary exposes server configuration, advertised tool information, call outcomes, and an initialized probe. Higher layers do not depend directly on SDK response objects.

### `spec.py`

Parses YAML into validated suite and case models. It rejects malformed structures and unknown expectation keys before starting the server. Relative working directories and file paths are resolved from the suite file's directory.

### `assertions.py`

Contains pure functions that compare a normalized call outcome with case expectations. It has no subprocess, MCP session, terminal, or filesystem responsibility.

### `runner.py`

Runs cases sequentially against one server process per suite. It coordinates calls and assertions and returns structured results without formatting them.

### `report.py` and `junit.py`

Transform structured results into terminal text and JUnit XML. Formatting remains independent from execution.

### `checks.py` and `lint.py`

Implement test-free protocol checks and pure tool-definition quality checks. Protocol checks use the same client probe as the suite runner. Linting operates only on normalized tool descriptions and schemas.

### `cli.py`

Provides a thin command-line boundary for `run` and `check`. It parses arguments, calls application functions, renders results, unwraps infrastructure errors into concise messages, and selects the documented exit code.

## Data Flow

The `run` flow is:

```text
YAML suite -> spec parser -> suite runner -> stdio client -> MCP server
                                  |
                                  v
                              assertions
                                  |
                                  v
                       terminal or JUnit report
```

The `check` flow is:

```text
server command -> stdio client -> protocol checks
                              -> tool-definition lint
                              -> terminal report
```

## CLI Contract

Primary commands:

```bash
mcp-rig run tests/mcp.yaml
mcp-rig run tests/mcp.yaml --junit report.xml
mcp-rig check "python server.py"
mcp-rig check "python server.py" --strict
```

Common diagnostics may expose server stderr through `--server-logs`; server stderr is suppressed by default so it does not corrupt MCP Rig's report.

Exit codes:

- `0`: every requested test or protocol check passed.
- `1`: execution was valid, but a test/check failed; for `check --strict`, lint warnings also produce `1`.
- `2`: invocation, configuration, suite parsing, server startup, or other infrastructure failure prevented a valid run.

## YAML Contract

Canonical form:

```yaml
server:
  command: python
  args: [server.py]

tests:
  - name: add returns five
    call: add
    args:
      a: 2
      b: 3
    expect:
      is_error: false
      contains: "5"
      max_latency_ms: 1000
```

For convenience, the server may also be written as a shell-like command string:

```yaml
server: "python server.py"
```

Each case supports a name, tool name, argument mapping, timeout, and expectation mapping. An omitted or empty `expect` means the tool call must succeed.

Supported expectation keys:

- `is_error`
- `contains`
- `not_contains`
- `matches`
- `max_latency_ms`
- `json_path`
- `schema`

Unknown keys are configuration errors rather than ignored fields.

## Runtime and Error Semantics

A tool-level MCP error is a normal call outcome. It is available to `is_error` and content assertions and does not by itself mean MCP Rig failed to execute the suite.

Subprocess startup failures, session initialization failures, unexpected connection loss, and case timeouts are infrastructure errors with explicit reporting. They must not be presented as ordinary assertion mismatches.

One server process is used for the complete suite. This reduces startup overhead and permits stateful sequences. Cases run sequentially in YAML order.

Server stderr is hidden by default and may be enabled for diagnosis. MCP protocol traffic over stdout must never be mixed with MCP Rig's own terminal output.

## Safety

Default checks may list tools, call a guaranteed-unknown tool name, and verify that the server remains responsive. They do not invoke advertised tools with fabricated arguments.

Invalid-argument probing is opt-in through `--probe-invalid-args`, because a server without argument validation might execute a real side effect. Documentation and terminal help must state this risk.

MCP Rig makes no claim that an arbitrary tool is safe to execute. YAML-authored tool calls are treated as explicit user intent.

## Testing Strategy

Development is test-first.

- Pure components (`spec`, `assertions`, `lint`, `report`, and `junit`) use fast unit tests without a live server.
- Client, runner, checks, and CLI use a controlled fixture server through a real stdio MCP session.
- CLI tests verify exit codes and user-visible output, not only internal function results.
- Dedicated cases cover timeout, malformed YAML, unknown tools, MCP tool errors, server termination, and unknown expectation keys.
- Every phase gate runs the complete pytest suite and Ruff across source and tests.
- Before release, an independent example stdio MCP server provides an interoperability smoke test.
- Release verification builds the wheel and installs it into a clean environment before exercising the installed CLI.

## Relationship to the Existing Claude Plan

`docs/plans/2026-09-25-mcptest-mvp.md` is an implementation reference containing prewritten code and tests. It is not an authority over observed SDK behavior or this approved design.

During implementation:

- Reuse plan code when it matches the approved contract and current SDK.
- Rename all public and internal project identity from `mcptest` to MCP Rig conventions.
- Preserve useful measured SDK behavior as regression tests.
- Change plan code when current API behavior, test quality, safety, or phase boundaries require it.
- Judge success by verified behavior, not by textual fidelity to the plan.
