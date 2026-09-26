# MCP Rig Server Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a test-file-free `mcp-rig check` command that verifies essential stdio tool behavior, lints tool definitions, and exposes deterministic output and exit codes.

**Architecture:** Keep runtime protocol probes in a focused `checks.py` module and pure metadata analysis in `lint.py`. The CLI owns connection orchestration and exit policy, while `report.py` only formats the structured results; the existing `run` workflow remains unchanged.

**Tech Stack:** Python 3.11+, MCP Python SDK 2.x, AnyIO, jsonschema Draft 2020-12, argparse, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-27-server-checks-design.md`

## Global Constraints

- Support only local stdio server commands; do not add remote transports.
- Keep `--probe-invalid-args` disabled by default and describe it as development/test-only.
- Preserve the existing `mcp-rig run` arguments, output, JUnit behavior, and exit codes.
- Use exit code `0` for passing checks, `1` for protocol failure or strict lint failure, and `2` for command/setup/transport/teardown failure outside a captured probe.
- Keep result and warning order deterministic.
- Do not add configurable lint thresholds, retries, restarts, or automatic fixes.

## Review Focus

- An advertised tool named like the reserved unknown-tool probe must never be invoked; test deterministic collision avoidance in Task 1.
- A malformed schema `required` value must not trigger an empty-argument tool call; test safe selection in Task 1.
- A call exception must remain a failed check while the final liveness probe still runs; test both results in Task 1.
- A malformed schema or non-mapping `properties` value must produce lint output without crashing; test both in Task 2.
- Whitespace-only descriptions on tools and parameters must count as missing; test both in Task 2.

---

### Task 1: Protocol Check Engine

**Files:**
- Create: `src/mcp_rig/checks.py`
- Create: `tests/test_checks.py`

**Interfaces:**
- Consumes: `Probe.list_tools() -> list[ToolInfo]` and `Probe.call(name, args, timeout_s) -> CallOutcome` from `src/mcp_rig/client.py`.
- Produces: frozen `CheckResult(name: str, passed: bool, detail: str = "")`, `UNKNOWN_TOOL_BASE = "__mcp_rig_unknown_tool__"`, and `async run_protocol_checks(probe: Probe, probe_invalid_args: bool = False) -> list[CheckResult]`.

- [ ] **Step 1: Write failing integration tests for the default checks**

Add `test_default_checks_pass_on_fixture` and assert the exact ordered names:

```python
[
    "lists tools",
    "unknown tool returns an error",
    "server alive after bad calls",
]
```

Assert every result passes against `fixture_spec` through the real `connect()` boundary.

- [ ] **Step 2: Run the default-check test and verify RED**

Run: `pytest tests/test_checks.py::test_default_checks_pass_on_fixture -q`

Expected: collection fails because `mcp_rig.checks` does not exist.

- [ ] **Step 3: Implement the minimal default check engine**

Create the public interfaces above. List tools, emit the non-empty discovery
result, call `UNKNOWN_TOOL_BASE`, require an in-band `is_error=True` outcome,
and finish with a second `list_tools()` liveness call. Catch ordinary
`Exception` around negative calls and final liveness only; do not catch
cancellation or process-level base exceptions. Collision avoidance and precise
failure details remain for the next RED→GREEN cycle.

- [ ] **Step 4: Run the default-check test and verify GREEN**

Run: `pytest tests/test_checks.py::test_default_checks_pass_on_fixture -q`

Expected: `1 passed`.

- [ ] **Step 5: Write failing focused tests for negative-probe edge cases**

Using small async fake probes, add tests that assert:

- an advertised `UNKNOWN_TOOL_BASE` causes the call to use `f"{UNKNOWN_TOOL_BASE}_2"`;
- unexpected success produces `passed is False` and a detail containing `expected is_error=true`;
- a raised `RuntimeError("boom")` produces a failed negative-call result, and a later `list_tools()` call still produces the liveness result;
- a failed final `list_tools()` produces `server alive after bad calls` with `passed is False` and the exception type/message in `detail`.

- [ ] **Step 6: Run the focused tests and verify RED**

Run: `pytest tests/test_checks.py -q`

Expected: the new edge-case assertions fail because collision handling and failure details are incomplete.

- [ ] **Step 7: Complete negative-probe behavior**

Keep helper functions private. Choose an unknown name absent from the
advertised names by appending `_2`, `_3`, and so on to the base when needed.
Format raised-call details as `call raised <Type> instead of returning
is_error: <message>` and liveness details as `<Type>: <message>`. Limit
successful response excerpts in failure details to 80 characters.

- [ ] **Step 8: Run protocol tests and verify GREEN**

Run: `pytest tests/test_checks.py -q`

Expected: all protocol tests pass.

- [ ] **Step 9: Write failing tests for opt-in invalid-argument probes**

Add a real-fixture test asserting `add: missing required args rejected` and `get_user: missing required args rejected` appear only with `probe_invalid_args=True`. Add a fake-probe test whose tools contain valid required fields, an empty list, a string, and a mixed-type list; assert only the non-empty all-string list causes a call.

- [ ] **Step 10: Run the invalid-argument tests and verify RED**

Run: `pytest tests/test_checks.py -q`

Expected: assertions fail because invalid-argument probes are not implemented.

- [ ] **Step 11: Implement safe invalid-argument selection**

For each discovered tool in order, call it with `{}` only when `required` is a non-empty list and every member is a string. Insert these results after the unknown-tool result and before final liveness. Reuse the same in-band error evaluator with a 10-second timeout.

- [ ] **Step 12: Run the task verification**

Run: `pytest tests/test_checks.py -q && pytest -q && ruff check src tests`

Expected: all checks pass.

- [ ] **Step 13: Commit the protocol engine**

```bash
git add src/mcp_rig/checks.py tests/test_checks.py
git commit -m "feat: add stdio protocol checks"
```

---

### Task 2: Tool Definition Lint

**Files:**
- Create: `src/mcp_rig/lint.py`
- Create: `tests/test_lint.py`

**Interfaces:**
- Consumes: `ToolInfo(name: str, description: str, input_schema: dict[str, Any])` from `src/mcp_rig/client.py`.
- Produces: frozen `LintWarning(tool: str, code: str, message: str)`, `MIN_DESCRIPTION_WORDS = 5`, `SIMILARITY_THRESHOLD = 0.85`, and `lint_tools(tools: list[ToolInfo]) -> list[LintWarning]`.

- [ ] **Step 1: Write failing description-lint tests**

Add tests for a clean tool, empty and whitespace-only descriptions producing `no-description`, and four-word descriptions producing `short-description` with `description has 4 words (min 5)`.

- [ ] **Step 2: Run description tests and verify RED**

Run: `pytest tests/test_lint.py -q`

Expected: collection fails because `mcp_rig.lint` does not exist.

- [ ] **Step 3: Implement description lint**

Create the public interfaces and private description helper. Use `description.split()` for word counting and preserve input tool order.

- [ ] **Step 4: Run description tests and verify GREEN**

Run: `pytest tests/test_lint.py -q`

Expected: all current lint tests pass.

- [ ] **Step 5: Write failing schema-lint tests**

Add tests asserting:

- `{"type": "not-a-type"}` produces only `invalid-schema`;
- a valid property without `description`, or with whitespace-only `description`, produces `param-no-description`;
- a malformed non-mapping `properties` value produces `invalid-schema` without raising;
- a schema with described properties produces no schema warning.

- [ ] **Step 6: Run schema tests and verify RED**

Run: `pytest tests/test_lint.py -q`

Expected: schema warning assertions fail because schema lint is absent.

- [ ] **Step 7: Implement schema lint**

Validate with `jsonschema.Draft202012Validator.check_schema`. On `jsonschema.SchemaError`, emit one `invalid-schema` warning with `exc.message` and skip property traversal. For a valid schema, emit one `param-no-description` warning per property whose description is missing, non-string, or whitespace-only.

- [ ] **Step 8: Run schema tests and verify GREEN**

Run: `pytest tests/test_lint.py -q`

Expected: all current lint tests pass.

- [ ] **Step 9: Write failing similarity and ordering tests**

Add tests asserting descriptions with a `SequenceMatcher` ratio equal to or above `0.85` produce one `similar-tools` warning named `first/second`, dissimilar and undocumented tools do not, each unordered pair appears once, and complete output order is per-tool description/schema warnings followed by similarity warnings.

- [ ] **Step 10: Run similarity tests and verify RED**

Run: `pytest tests/test_lint.py -q`

Expected: similarity assertions fail because pairwise lint is absent.

- [ ] **Step 11: Implement deterministic similarity lint**

Compare lowercased non-empty descriptions with `difflib.SequenceMatcher`. Iterate pairs in input order and emit `descriptions are <rounded-percent> similar; models may confuse them` at or above the fixed threshold.

- [ ] **Step 12: Add and pass the real-fixture lint test**

Connect to `fixture_spec`, lint `await probe.list_tools()`, and assert at least `("undocumented", "no-description")` and `("add", "param-no-description")` are present.

Run: `pytest tests/test_lint.py -q && pytest -q && ruff check src tests`

Expected: all checks pass.

- [ ] **Step 13: Commit tool lint**

```bash
git add src/mcp_rig/lint.py tests/test_lint.py
git commit -m "feat: lint MCP tool definitions"
```

---

### Task 3: Check Report Rendering

**Files:**
- Modify: `src/mcp_rig/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: `CheckResult` from Task 1 and `LintWarning` from Task 2.
- Produces: `YELLOW = "\033[33m"` and `render_check(checks: list[CheckResult], warnings: list[LintWarning], color: bool = False) -> str`.

- [ ] **Step 1: Write the failing exact-output report test**

For one passing check, one failed check with `got success`, and one lint warning, assert exact output containing these sections and summary:

```text
Protocol checks
  ✓ lists tools
  ✗ unknown tool returns an error
      got success
Lint
  ⚠ undocumented [no-description] tool has no description
1/2 checks passed, 1 lint warning
```

Also add a test that an empty warning list renders `  no warnings` and pluralizes `warnings` only when the count is not one.

- [ ] **Step 2: Run report tests and verify RED**

Run: `pytest tests/test_report.py -q`

Expected: import fails because `render_check` does not exist.

- [ ] **Step 3: Implement the pure check renderer**

Add `YELLOW` and the exact public signature. Reuse `_paint`, keep existing suite output unchanged, indent failure details by six spaces, and color only the three status symbols.

- [ ] **Step 4: Run report tests and verify GREEN**

Run: `pytest tests/test_report.py -q`

Expected: all report tests pass.

- [ ] **Step 5: Add and pass focused color tests**

Assert `color=True` wraps `✓`, `✗`, and `⚠` with their expected ANSI codes while headings, details, and summary text remain uncolored.

Run: `pytest tests/test_report.py -q && pytest -q && ruff check src tests`

Expected: all checks pass.

- [ ] **Step 6: Commit check reporting**

```bash
git add src/mcp_rig/report.py tests/test_report.py
git commit -m "feat: render protocol and lint results"
```

---

### Task 4: Public `check` CLI Workflow

**Files:**
- Modify: `src/mcp_rig/cli.py`
- Modify: `tests/test_cli.py`
- Create: `tests/fixtures/stderr_server.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `run_protocol_checks` from Task 1, `lint_tools` from Task 2, `render_check` from Task 3, and existing `ServerSpec`/`connect` interfaces.
- Produces: `mcp-rig check SERVER [--probe-invalid-args] [--strict] [--server-logs]`, `_check(spec: ServerSpec, probe_invalid_args: bool, show_server_logs: bool) -> tuple[list[CheckResult], list[LintWarning]]`, and unchanged public `main(argv=None) -> int` behavior for `run`.

- [ ] **Step 1: Write failing default and strict CLI tests**

Add `test_check_passes_with_lint_warnings` asserting exit `0`, all three default checks, the fixture's `undocumented [no-description]` warning, and no traceback. Add `test_check_strict_fails_on_lint_warnings` asserting exit `1` with the same report.

- [ ] **Step 2: Run default CLI tests and verify RED**

Run: `pytest tests/test_cli.py -k 'check_passes_with_lint or check_strict' -q`

Expected: argparse rejects the missing `check` command.

- [ ] **Step 3: Add check parser, dispatch, and orchestration**

Create the `check` subparser and flags from the public interface. Rename the current `_run` helper to `_cmd_run` without changing its behavior. `_check` captures tool definitions, runs protocol checks within the same connection, then returns checks plus pure lint output. `_cmd_check` prints `render_check` and applies the specified exit policy.

- [ ] **Step 4: Run default CLI tests and verify GREEN**

Run: `pytest tests/test_cli.py -k 'check_passes_with_lint or check_strict' -q`

Expected: `2 passed`.

- [ ] **Step 5: Write failing safety, error, and log-routing tests**

Add tests asserting:

- `--probe-invalid-args` reports the fixture's required-argument checks and exits `0`;
- an empty server command and a definitely missing executable each exit `2`, write a concise `error:` to stderr, and emit no traceback;
- default check hides `mcp-rig-check-server-log`, while `--server-logs` exposes it when running `tests/fixtures/stderr_server.py`.

The fixture wrapper prints the marker to stderr before starting the existing fixture server.

- [ ] **Step 6: Run the focused tests and verify RED**

Run: `pytest tests/test_cli.py -k 'probe_invalid_args or check_empty or check_unstartable or check_server_logs' -q`

Expected: one or more new assertions fail because the corresponding CLI behavior or fixture is absent.

- [ ] **Step 7: Complete CLI error and log behavior**

Convert `ServerSpec.from_command_line` and connection failures into exit `2` with `_describe`; rely on `connect(..., show_server_logs=...)` for stderr routing. Do not change suite-run exception or JUnit behavior.

- [ ] **Step 8: Run CLI and regression verification**

Run: `pytest tests/test_cli.py -q && pytest -q && ruff check src tests`

Expected: all checks pass, including every existing `run` test.

- [ ] **Step 9: Document the check command**

Add README examples for default, strict, invalid-argument, and server-log modes. State that invalid-argument probing can execute incorrectly validated tools and must only be used against development/test servers. Document exit codes `0`, `1`, and `2` for `check`.

- [ ] **Step 10: Verify installed-package behavior**

Install the current project into a temporary virtual environment, run `mcp-rig check` against `tests/fixtures/fixture_server.py`, and verify the report contains `3/3 checks passed` with exit `0`. Run strict mode and verify lint warnings produce exit `1`.

- [ ] **Step 11: Run final branch verification**

Run: `pytest -q && ruff check src tests && python -m pip check && git diff --check origin/main..HEAD`

Expected: all tests and lint pass, dependencies are consistent, and the committed diff has no whitespace errors.

- [ ] **Step 12: Commit the public workflow**

```bash
git add src/mcp_rig/cli.py tests/test_cli.py tests/fixtures/stderr_server.py README.md
git commit -m "feat: add server check command"
```
