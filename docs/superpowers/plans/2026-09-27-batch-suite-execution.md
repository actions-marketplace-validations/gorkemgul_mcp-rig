# Batch Suite Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `mcp-rig run` so one invocation executes deterministic batches of suite files and recursively discovered suite directories with aggregate terminal and JUnit reporting.

**Architecture:** A new discovery module turns CLI targets into ordered paths and structured target errors. A new batch module parses and runs those paths sequentially through the existing `load_suite` and `run_suite` boundaries, while the terminal and JUnit layers consume one aggregate result model.

**Tech Stack:** Python 3.11+, argparse, pathlib/os, anyio, dataclasses, StrEnum, xml.etree.ElementTree, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-27-batch-suite-execution-design.md`

## Global Constraints

- Preserve local stdio servers and tool calls as the only MCP transport and surface.
- Preserve exit codes: `0` success, `1` assertion failures only, `2` any configuration, infrastructure, or report-writing error.
- Run suites sequentially in deterministic normalized absolute-path order.
- Recursively discover only `.yaml` and `.yml`; do not add internal glob expansion.
- Continue with other suites after target, parse, startup, transport, or teardown errors.
- Preserve byte-for-byte terminal output for a successful one-file invocation.
- Keep server stderr hidden unless `--server-logs` is supplied.
- Add no runtime dependency.
- Run commands from the repository root with the development environment activated and `PYTHONPATH=src`.

## Review Focus

- The same suite reached through relative, absolute, directory, or symlink paths runs once; Task 1 pins canonical deduplication.
- A traversal error in one directory does not discard files from valid targets; Task 1 pins partial discovery.
- A JUnit destination nested inside an input directory cannot overwrite a discovered suite; Task 5 pins collision detection after discovery and before execution.
- `KeyboardInterrupt`, cancellation, and other `BaseException` values are never converted into suite errors; Task 2 pins propagation.
- Mixed assertion and infrastructure failures still run every suite and exit `2`; Tasks 2 and 5 pin precedence and continuation.

---

### Task 1: Deterministic Target Discovery

**Files:**
- Create: `src/mcp_rig/discovery.py`
- Create: `tests/test_discovery.py`

**Interfaces:**
- Consumes: CLI target strings or `Path` values.
- Produces: `DiscoveryError(target: Path, exception_type: str, message: str)`, `DiscoveryResult(paths: list[Path], errors: list[DiscoveryError])`, and `discover_suites(targets: Sequence[str | Path]) -> DiscoveryResult`.

- [ ] **Step 1: Write failing discovery tests**

Add tests named:

```python
def test_discovers_yaml_recursively_in_canonical_sorted_order(tmp_path): ...
def test_deduplicates_relative_absolute_directory_and_symlink_targets(tmp_path, monkeypatch): ...
def test_keeps_valid_paths_while_reporting_missing_unsupported_and_empty_targets(tmp_path): ...
def test_keeps_other_targets_when_directory_traversal_fails(tmp_path, monkeypatch): ...
```

Assert literal resolved path lists, `.yaml` and `.yml` inclusion, non-YAML exclusion inside directories, one structured error per bad target, and preserved valid paths after a simulated `PermissionError` from directory traversal.

- [ ] **Step 2: Run the discovery tests and verify RED**

Run: `PYTHONPATH=src python -m pytest -q tests/test_discovery.py`

Expected: collection fails because `mcp_rig.discovery` does not exist.

- [ ] **Step 3: Implement the discovery model and traversal**

Create the three interfaces above. Resolve every emitted file path, deduplicate by that resolved path, sort using `str(path)`, use recursive traversal without following directory symlinks, and convert filesystem failures into `DiscoveryError` without dropping successful results from other targets.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_discovery.py
ruff check src/mcp_rig/discovery.py tests/test_discovery.py
```

Expected: all discovery tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the discovery boundary**

```bash
git add src/mcp_rig/discovery.py tests/test_discovery.py
git commit --no-gpg-sign -m "feat: discover MCP suites from multiple targets"
```

### Task 2: Sequential Batch Execution

**Files:**
- Create: `src/mcp_rig/batch.py`
- Create: `tests/test_batch.py`

**Interfaces:**
- Consumes: Task 1 `DiscoveryResult`, `load_suite(path) -> Suite`, and `run_suite(suite, show_server_logs=False) -> SuiteResult`.
- Produces: `BatchFailureCategory(StrEnum)` with `CONFIGURATION` and `EXECUTION`; `BatchFailure(category, exception_type, message)`; `SuiteRun(path: Path, result: SuiteResult | None = None, error: BatchFailure | None = None)`; `BatchResult(suites: list[SuiteRun], discovery_errors: list[DiscoveryError])`; and `async run_batch(discovery: DiscoveryResult, show_server_logs: bool = False) -> BatchResult`.
- Produces aggregate `BatchResult` properties: `suite_passed`, `suite_failed`, `suite_errors`, `case_passed`, `case_failed`, `case_errors`, `case_skipped`, `has_failures`, and `has_errors`.

- [ ] **Step 1: Write failing batch model and orchestration tests**

Add tests named:

```python
def test_batch_counts_suite_and_case_outcomes_with_discovery_errors(): ...
@pytest.mark.anyio
async def test_batch_runs_paths_sequentially_and_forwards_server_logs(monkeypatch, tmp_path): ...
@pytest.mark.anyio
async def test_batch_continues_after_parse_and_execution_errors(monkeypatch, tmp_path): ...
@pytest.mark.anyio
async def test_batch_propagates_keyboard_interrupt(monkeypatch, tmp_path): ...
```

Use literal `SuiteResult` fixtures. A suite containing both a failed case and an infrastructure error counts as an errored suite, not a failed suite. Verify call order, continued execution, exact failure categories, all aggregate counts, and propagation of `KeyboardInterrupt`.

- [ ] **Step 2: Run the batch tests and verify RED**

Run: `PYTHONPATH=src python -m pytest -q tests/test_batch.py`

Expected: collection fails because `mcp_rig.batch` does not exist.

- [ ] **Step 3: Implement aggregate models and `run_batch`**

Catch `SpecError` as `CONFIGURATION` and ordinary unexpected `Exception` at a suite boundary as `EXECUTION`; do not catch `BaseException`. Reuse `run_suite` results for startup, transport, timeout, and teardown states. Implement aggregate properties from structured results only.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_batch.py tests/test_runner.py
ruff check src/mcp_rig/batch.py tests/test_batch.py
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit batch execution**

```bash
git add src/mcp_rig/batch.py tests/test_batch.py
git commit --no-gpg-sign -m "feat: execute MCP suites as a resilient batch"
```

### Task 3: Aggregate Terminal Reporting

**Files:**
- Modify: `src/mcp_rig/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: Task 2 `BatchResult`, `SuiteRun`, and existing `render_suite`.
- Produces: `render_batch_errors(result: BatchResult) -> str` for target/configuration/execution errors and `render_batch(result: BatchResult, color: bool = False) -> str` for suite output and aggregate counts.

- [ ] **Step 1: Write failing renderer tests**

Add tests named:

```python
def test_render_batch_preserves_single_successful_suite_output(): ...
def test_render_batch_reports_each_suite_then_literal_aggregate_counts(): ...
def test_render_batch_errors_identifies_target_and_suite_sources(): ...
def test_render_batch_colors_only_status_marks(): ...
```

Assert equality with `render_suite` for one valid suite. For a mixed batch, assert deterministic section order and the exact final lines:

```text
Suites: 1 passed, 1 failed, 2 errors
Cases: 3 passed, 1 failed, 1 error, 1 skipped
```

- [ ] **Step 2: Run renderer tests and verify RED**

Run: `PYTHONPATH=src python -m pytest -q tests/test_report.py`

Expected: new tests fail because batch renderers are missing.

- [ ] **Step 3: Implement batch renderers by composing `render_suite`**

Return the existing `render_suite` output unchanged when there is exactly one parsed suite and no discovery or batch failure. In every other case, render parsed suites in order, omit empty sections, and append aggregate suite/case lines. Render errors with their target or suite path and normalized category/type/message.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_report.py
ruff check src/mcp_rig/report.py tests/test_report.py
```

Expected: all report tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit terminal reporting**

```bash
git add src/mcp_rig/report.py tests/test_report.py
git commit --no-gpg-sign -m "feat: report aggregate MCP suite results"
```

### Task 4: Combined JUnit Reporting

**Files:**
- Modify: `src/mcp_rig/junit.py`
- Modify: `tests/test_junit.py`

**Interfaces:**
- Consumes: Task 2 `BatchResult` and existing `SuiteResult` case mapping.
- Produces: `write_batch_junit(path: str | Path, result: BatchResult) -> None`; preserves `write_junit(path, suite_name, result)` as a compatibility wrapper.

- [ ] **Step 1: Write failing multi-suite JUnit tests**

Add tests named:

```python
def test_write_batch_junit_emits_ordered_suite_children_and_root_totals(tmp_path): ...
def test_write_batch_junit_adds_synthetic_discovery_parse_and_execution_errors(tmp_path): ...
def test_write_junit_compatibility_wrapper_keeps_existing_document(tmp_path): ...
```

Assert one `<testsuite>` per ordered suite or invalid target, exact root `tests`, `failures`, `errors`, `skipped`, and `time` totals, unchanged case status mapping, and stable synthetic names `[target configuration]`, `[suite configuration]`, and `[suite execution]`.

- [ ] **Step 2: Run JUnit tests and verify RED**

Run: `PYTHONPATH=src python -m pytest -q tests/test_junit.py`

Expected: new tests fail because `write_batch_junit` is missing.

- [ ] **Step 3: Refactor one-suite XML construction and implement `write_batch_junit`**

Extract a private helper that appends one existing `SuiteResult` without changing its XML. Add synthetic error suites from discovery and `SuiteRun.error`, set aggregate root attributes from emitted child values, and continue to let filesystem write errors propagate.

- [ ] **Step 4: Run focused tests and Ruff**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_junit.py
ruff check src/mcp_rig/junit.py tests/test_junit.py
```

Expected: all JUnit tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit combined JUnit output**

```bash
git add src/mcp_rig/junit.py tests/test_junit.py
git commit --no-gpg-sign -m "feat: write combined JUnit suite reports"
```

### Task 5: Public CLI Integration and Documentation

**Files:**
- Modify: `src/mcp_rig/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 `discover_suites`, Task 2 `run_batch`, Task 3 renderers, and Task 4 `write_batch_junit`.
- Produces: public syntax `mcp-rig run TARGET [TARGET ...]` with unchanged flags and exit-code constants.

- [ ] **Step 1: Write failing CLI acceptance tests**

Add or update tests named:

```python
def test_run_accepts_multiple_files_and_recursive_directory_targets(...): ...
def test_run_continues_after_invalid_suite_and_returns_two(...): ...
def test_run_mixed_assertion_and_infrastructure_failures_returns_two(...): ...
def test_run_writes_synthetic_junit_for_missing_or_invalid_targets(...): ...
def test_junit_path_cannot_overwrite_suite_discovered_inside_directory(...): ...
def test_server_logs_flag_applies_to_every_suite(...): ...
def test_run_single_file_output_remains_unchanged(...): ...
```

Use real temporary suite files and the deterministic fixture server. Assert every suite marker appears, sorted execution/report order is stable, later suites run after earlier errors, `2` overrides `1`, combined JUnit exists for config errors, collision exits before server startup, and successful single-file output matches its pre-feature literal.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `PYTHONPATH=src python -m pytest -q tests/test_cli.py`

Expected: new batch invocations fail because argparse still accepts one suite and the CLI lacks batch coordination.

- [ ] **Step 3: Integrate discovery, collision checks, execution, reporting, and exit precedence**

Change the positional argument to `targets` with `nargs="+"`. Discover before checking JUnit collisions, reject any collision before parsing or server startup, run the batch with `anyio.run`, write normalized errors to stderr, render structured results to stdout, write combined JUnit when requested, and return `2` before `1` when both states exist.

- [ ] **Step 4: Document the public batch workflow**

Update README examples for one file, several files, and recursive directories. Document canonical deduplication, deterministic order, continuation after suite errors, aggregate exit codes, and one combined JUnit document.

- [ ] **Step 5: Run CLI and regression tests**

Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_cli.py tests/test_discovery.py tests/test_batch.py tests/test_report.py tests/test_junit.py
ruff check src tests scripts
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 6: Commit the public feature**

```bash
git add src/mcp_rig/cli.py tests/test_cli.py README.md
git commit --no-gpg-sign -m "feat: run multiple MCP suites from one command"
```

### Task 6: Full Verification and Release-Artifact Safety

**Files:**
- Modify only if verification exposes a defect in files already owned by Tasks 1–5.

**Interfaces:**
- Consumes: the complete batch feature.
- Produces: verified source tree, wheel, and source distribution ready for branch review.

- [ ] **Step 1: Run the complete local quality gate**

Run:

```bash
PYTHONPATH=src python -m pytest -q
ruff check src tests scripts
git diff --check
```

Expected: all tests pass, Ruff reports no errors, and `git diff --check` emits nothing.

- [ ] **Step 2: Build and validate distributions outside the worktree**

Run `python -m build` with an output directory under `/private/tmp`, then run `python -m twine check` on the resulting wheel and sdist.

Expected: both artifacts build and both pass Twine validation.

- [ ] **Step 3: Smoke-test the installed wheel with a batch command**

Create a temporary virtual environment, install only the built wheel and its dependencies, then run its `mcp-rig` executable against two fixture-backed suite files with `--junit`.

Expected: both suites pass, the command exits `0`, and the JUnit root contains two `<testsuite>` children.

- [ ] **Step 4: Inspect final branch state**

Run:

```bash
git status --short
git log --oneline --decorate origin/main..HEAD
```

Expected: no uncommitted files and the design plus five focused implementation commits are present.
