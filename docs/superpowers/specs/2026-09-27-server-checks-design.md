# MCP Rig Server Checks Design

## Purpose

Add a test-file-free way to evaluate a local stdio MCP server. A developer can
run one command to verify essential tool-call behavior, inspect tool-definition
quality, and receive stable terminal output and exit codes suitable for local
development and CI.

This increment extends the existing native `mcp-rig` CLI and reuses its stdio
client boundary. It does not change suite execution or add another transport.

## Scope

This increment adds:

- `mcp-rig check "<server command>"` for local stdio servers;
- protocol checks for tool discovery, unknown-tool errors, and server survival
  after deliberately bad calls;
- an opt-in probe for missing required tool arguments;
- static linting of tool descriptions and input schemas;
- terminal reporting for protocol checks and lint warnings;
- `--strict`, `--probe-invalid-args`, and `--server-logs` options;
- stable exit codes for success, check failure, strict lint failure, and
  infrastructure failure; and
- README documentation for the new workflow and its safety boundary.

The following remain out of scope:

- YAML suites or assertions in the `check` flow;
- resources, prompts, sampling, elicitation, or other MCP capabilities;
- HTTP, SSE, or other remote transports;
- calling tools with generated valid arguments;
- automatic fixes for lint warnings;
- configurable lint thresholds or warning suppression;
- retries, server restarts, or recovery after a broken transport;
- CI/release automation and PyPI publication.

## User Contract

The basic command is:

```text
mcp-rig check "python path/to/server.py"
```

The server command is parsed with the existing `ServerSpec.from_command_line`
behavior, connected over stdio, and started once for the complete check run.
Server stderr remains hidden unless `--server-logs` is supplied.

The command supports:

- `--strict`: make any lint warning fail the command;
- `--probe-invalid-args`: call tools that declare required input fields with an
  empty argument object; and
- `--server-logs`: forward the child server's stderr.

`--probe-invalid-args` is disabled by default. A server that fails to enforce
its declared schema might execute a tool body when called with empty arguments.
The help text and README explicitly restrict this option to development and
test servers where that risk is acceptable.

## Protocol Checks

`checks.py` owns an immutable `CheckResult` with `name`, `passed`, and an
optional `detail`. `run_protocol_checks(probe, probe_invalid_args=False)`
returns results in deterministic execution order.

The default checks are:

1. `lists tools`: `tools/list` completes and returns at least one tool.
2. `unknown tool returns an error`: calling a reserved nonexistent tool name
   completes with `CallOutcome.is_error == True` rather than reporting success
   or raising at the client boundary.
3. `server alive after bad calls`: a final `tools/list` completes, proving the
   session still responds after the negative probe.

With `--probe-invalid-args`, one additional check is inserted for every tool
whose input schema contains a non-empty `required` array made entirely of
strings. Each such tool is called with `{}` and must return
`is_error == True`. Tools without required fields, and tools whose malformed
schema does not safely identify required fields, are not called. Schema lint
reports the malformed definition separately.

The unknown-tool probe begins with a reserved base name and verifies it is not
present in the discovered inventory. If it collides, MCP Rig appends a
deterministic suffix until the name is absent, so the negative probe never
invokes a real advertised tool. Call exceptions become failed protocol results
with concise details; they are not mistaken for the expected in-band MCP tool
error. The final liveness check is still attempted so the report distinguishes
a single bad response from a damaged session. Cancellation and process-level
base exceptions are not swallowed.

## Tool Definition Lint

`lint.py` owns an immutable `LintWarning` with `tool`, `code`, and `message`.
`lint_tools(tools)` is pure and returns warnings in stable order: per-tool
description warnings, per-tool schema warnings, then pairwise similarity
warnings.

The initial warning codes are:

| Code | Condition |
| --- | --- |
| `no-description` | The tool description is empty or whitespace-only. |
| `short-description` | The description contains fewer than five whitespace-separated words. |
| `invalid-schema` | The input schema is not valid JSON Schema Draft 2020-12. |
| `param-no-description` | A property in a valid object schema lacks a non-empty description. |
| `similar-tools` | Two documented tools have descriptions at least 85% similar. |

Schema validation happens before property inspection. An invalid schema emits
one `invalid-schema` warning and is not traversed further, preventing malformed
schema structures from crashing lint. Similarity comparison is case-insensitive
and uses `difflib.SequenceMatcher`; each unordered tool pair is considered
once in input order. Empty descriptions do not participate in similarity
checks.

These are advisory quality signals rather than proof that a model will or will
not choose the right tool. The fixed thresholds keep the first public contract
small and deterministic; configuration can be considered after real usage.

## Execution and Data Flow

The CLI establishes one connection and performs the work in this order:

```text
server command
    -> ServerSpec.from_command_line
    -> connect over stdio
    -> list tools for lint input
    -> run protocol checks
    -> close connection
    -> lint captured tool definitions
    -> render one combined report
    -> choose exit code
```

The initial tool list used for lint is captured while the connection is open.
The protocol checker performs its own first and final `tools/list` operations
because discovery and post-error liveness are behaviors being tested, not only
data-loading steps. Lint runs after the connection closes and performs no I/O.

The existing `Probe`, `ToolInfo`, `CallOutcome`, and `connect` interfaces remain
unchanged. Suite parsing, suite execution, assertions, and JUnit reporting are
not involved in this command.

## Terminal Reporting

`report.py` gains `render_check(checks, warnings, color=False)`. Output has a
`Protocol checks` section followed by a `Lint` section and a final summary.

- Passing checks use `✓`.
- Failed checks use `✗` followed by an indented detail when available.
- Lint warnings use `⚠` and include the tool name, stable warning code, and
  message.
- An empty warning list renders `no warnings` rather than an empty section.
- Color is limited to status symbols and follows the existing TTY decision.

Rendering is pure: it does not inspect SDK values, run lint, or infer failures.

## Exit Codes and Errors

The command follows the existing CLI contract:

- `0`: every protocol check passed; lint warnings are allowed without
  `--strict`;
- `1`: at least one protocol check failed, or `--strict` was supplied and at
  least one lint warning exists; and
- `2`: the server command is invalid, the process cannot start, initialization
  fails, the transport breaks outside a captured protocol probe, or teardown
  fails.

Protocol failure takes precedence over lint policy but both produce exit code
1. Infrastructure failure produces exit code 2 and a concise stderr message
without a traceback. Nested exception groups are reduced through the existing
CLI exception-description helper.

When connection setup fails there is no partial check or lint report because
no reliable tool inventory exists. A failed negative probe that remains inside
`run_protocol_checks` is instead represented in the normal report, including
the final liveness result.

## Architecture and File Changes

### `src/mcp_rig/checks.py`

Define protocol result values, the reserved unknown-tool name, ordered check
execution, negative-call evaluation, and final session-liveness evaluation.

### `src/mcp_rig/lint.py`

Define warning values and pure description, schema, property-description, and
similarity lint helpers.

### `src/mcp_rig/report.py`

Add the yellow status color and combined check/lint renderer without changing
the existing suite report contract.

### `src/mcp_rig/cli.py`

Add the `check` parser, dispatch, async orchestration, error conversion, and
exit-code policy. The existing `run` arguments and behavior remain backward
compatible.

### Tests and documentation

Add focused unit tests for protocol result construction, lint ordering and
edge cases, terminal rendering, CLI flags, exit codes, and server-log routing.
Extend the deterministic fixture server only where a behavior cannot be tested
through its current tools. Document safe usage in `README.md`.

## Testing Strategy

Development remains test-first.

- Protocol tests use a connected fixture server and focused fake probes to
  cover empty discovery, unexpected success, raised calls, invalid-argument
  selection, result ordering, and liveness failure.
- Lint unit tests cover each warning independently, malformed schema safety,
  deterministic ordering, whitespace-only descriptions, similarity boundaries,
  and clean tool definitions.
- Reporter tests assert exact uncolored output plus focused color behavior.
- CLI integration tests cover default success with warnings, strict failure,
  opt-in invalid-argument probes, hidden and visible server logs, malformed or
  empty server commands, startup failures, and traceback suppression.
- The full suite, Ruff, dependency check, and an installed-package smoke run of
  `mcp-rig check` are required before the branch is considered complete.

## Success Criteria

The increment is complete when:

- a developer can check a local stdio MCP server without authoring YAML;
- destructive-risk probes never run unless explicitly requested;
- protocol failures, lint warnings, and infrastructure failures remain visibly
  distinct;
- `--strict` makes lint enforceable in CI without changing the default local
  experience;
- all output and result ordering is deterministic; and
- the existing `mcp-rig run` workflow remains behaviorally unchanged.
