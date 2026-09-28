# Test Filtering and Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic case-name and inherited-tag filtering to `mcp-rig run` without starting servers for suites that have no selected cases.

**Architecture:** Parse immutable suite and case tag sets in the existing specification layer, then apply a new pure selection layer between suite loading and batch execution. Batch results carry global selection counts; the CLI and reporters expose those counts only when filters are active, while the runner remains unaware of filtering.

**Tech Stack:** Python 3.11+, `argparse`, `dataclasses`, `fnmatch`, PyYAML, AnyIO, pytest, Ruff, `build`, Twine

**Spec:** `docs/superpowers/specs/2026-09-28-test-filtering-tags-design.md`

## Global Constraints

- Preserve byte-for-byte terminal and JUnit behavior when no filter options are supplied.
- Tags must match `[a-z0-9][a-z0-9_-]*`; duplicate YAML and CLI tags use set semantics.
- Suite tags and case tags are immutable, and effective tags are their set union.
- Repeated `--case` values use OR; repeated `--tag` values use AND; any matching `--exclude-tag` removes a case.
- Filter dimensions combine with AND semantics and use case-sensitive shell-style glob matching.
- Every discovered suite is parsed and validated even when all of its cases are filtered out.
- A suite with zero selected cases must not start an MCP process or create an empty `SuiteRun`.
- Filtered-out cases are not skipped cases and never appear in JUnit.
- A global zero-match selection returns exit code `2`; requested JUnit output is still written.
- Do not add `--exclude-case`, boolean tag expressions, regex matching, suite-path filters, snapshots, or parallel execution.
- Use public-behavior TDD for every behavior change; do not commit generated distributions or temporary smoke-test files.

## Review Focus

- A tag included and excluded in the same invocation must produce a clean zero-match usage result without starting a server; Task 4 pins this through the public CLI.
- Non-list tag containers, non-string list members, uppercase tags, and leading punctuation must raise contextual configuration errors; Task 1 tests each input class.
- Glob metacharacters and case differences must follow `fnmatchcase`, not platform-dependent or substring matching; Task 1 tests literal expected selections.
- A filtered batch containing both a valid selected suite and a malformed suite must still report the malformed suite and return exit code `2`; Task 4 covers this mixed batch.
- A selected case that triggers an infrastructure failure may skip later selected cases, but filtered-out cases must remain absent from skip counts and JUnit; Tasks 2 and 3 cover this boundary.

---

## File Structure

- Create `src/mcp_rig/selection.py`: tag validation, immutable filter values, effective-tag matching, and pure suite selection.
- Create `tests/test_selection.py`: selector truth table, inheritance, glob behavior, ordering, and input-boundary tests.
- Modify `src/mcp_rig/spec.py`: immutable suite/case tag fields and contextual YAML validation.
- Modify `tests/test_spec.py`: tag parsing, defaults, deduplication, and invalid configuration coverage.
- Modify `src/mcp_rig/batch.py`: apply selection before execution and aggregate selection counts.
- Modify `tests/test_batch.py`: execution isolation, mixed-suite behavior, counters, and runtime skip boundaries.
- Modify `src/mcp_rig/report.py`: render selection counts only for filtered runs.
- Modify `tests/test_report.py`: single-suite and batch selection output plus no-filter compatibility.
- Modify `src/mcp_rig/junit.py` only if tests expose a missing empty-report or aggregate-count behavior.
- Modify `tests/test_junit.py`: selected-only cases, runtime skips, and valid empty reports.
- Modify `src/mcp_rig/cli.py`: repeatable filter arguments, CLI tag validation, zero-match exit behavior, and filter wiring.
- Modify `tests/test_cli.py`: public commands, combined filters, validation, no-server guarantees, errors, JUnit, and compatibility.
- Modify `README.md`: English YAML and CLI examples for tags and filtering.

### Task 1: Tag Model and Pure Selection

**Files:**
- Create: `src/mcp_rig/selection.py`
- Create: `tests/test_selection.py`
- Modify: `src/mcp_rig/spec.py`
- Modify: `tests/test_spec.py`

**Interfaces:**
- Consumes: existing `mcp_rig.spec.Suite(path, server, cases)` and `Case(name, call, args, expect, timeout_s)` models.
- Produces: `Case.tags: frozenset[str]`, `Suite.tags: frozenset[str]`, `validate_tag(value: object) -> str`, `SelectionFilter(case_patterns: tuple[str, ...] = (), required_tags: frozenset[str] = frozenset(), excluded_tags: frozenset[str] = frozenset())`, `SelectionFilter.active: bool`, `SuiteSelection(suite: Suite, selected: int, filtered_out: int)`, and `select_suite(suite: Suite, filters: SelectionFilter) -> SuiteSelection`.

- [ ] **Step 1: Write failing specification tests for tag defaults and parsing**

Add tests named `test_tags_default_to_empty_immutable_sets`, `test_parses_and_deduplicates_suite_and_case_tags`, and a parameterized `test_rejects_invalid_tags_with_location` in `tests/test_spec.py`. Assert literal `frozenset()` defaults; suite tags `playwright, playwright` become `frozenset({"playwright"})`; case tags `smoke, browser` are preserved; and these inputs raise `SpecError` with the suite/case location: `tags: smoke`, `tags: [smoke, 3]`, `tags: [Smoke]`, `tags: [-slow]`, and an empty tag.

- [ ] **Step 2: Run the focused specification tests and verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_spec.py -q`

Expected: FAIL because `Suite` and `Case` do not expose tags and the parser ignores or mishandles the new fields.

- [ ] **Step 3: Implement immutable tag parsing in `spec.py`**

Add `tags: frozenset[str] = field(default_factory=frozenset)` as the final field on both models so current positional construction remains valid. Parse top-level and case-level `tags` through a small contextual helper that requires a list, calls `selection.validate_tag` for each member, deduplicates into `frozenset`, and translates `ValueError` into `SpecError` containing the existing suite/test location.

- [ ] **Step 4: Run the focused specification tests and verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_spec.py -q`

Expected: all specification tests pass.

- [ ] **Step 5: Write failing pure-selector tests**

In `tests/test_selection.py`, add literal cases covering:

- `validate_tag` accepts `smoke`, `browser-tools`, and `ci_fast`, and rejects uppercase, whitespace, empty, non-string, and leading punctuation;
- suite tags are inherited through effective union without mutating `Case.tags`;
- `--case` patterns use case-sensitive `fnmatchcase` behavior and repeated patterns are OR;
- required tags are AND;
- excluded tags are any-match exclusion;
- name, required-tag, and excluded-tag dimensions compose with AND;
- selected cases retain declaration order;
- selected and filtered-out counts sum to the original case count;
- no filters return an equivalent suite and `SelectionFilter.active is False`;
- the same included and excluded tag selects zero cases.

- [ ] **Step 6: Run selector tests and verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_selection.py -q`

Expected: FAIL because `mcp_rig.selection` and its interfaces do not exist.

- [ ] **Step 7: Implement the pure selection module**

Use a compiled full-match tag expression for `validate_tag`. Implement immutable dataclasses with the exact interfaces above. Avoid a runtime import cycle: `selection.py` may import `Suite` only under `TYPE_CHECKING`, because `spec.py` imports `validate_tag`; `dataclasses.replace` does not require the concrete class at runtime. Use `fnmatch.fnmatchcase(case.name, pattern)`, `required_tags.issubset(effective_tags)`, and `effective_tags.isdisjoint(excluded_tags)`. Return a new suite with `dataclasses.replace`; never mutate the input suite or case objects.

- [ ] **Step 8: Run Task 1 tests and the existing spec/runner slice**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_selection.py tests/test_spec.py tests/test_runner.py -q`

Expected: all selected tests pass and existing positional model construction remains compatible.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/mcp_rig/selection.py src/mcp_rig/spec.py tests/test_selection.py tests/test_spec.py
git commit -m "feat: add suite and case selection model"
```

### Task 2: Batch Selection and Execution Isolation

**Files:**
- Modify: `src/mcp_rig/batch.py`
- Modify: `tests/test_batch.py`

**Interfaces:**
- Consumes: Task 1 `SelectionFilter`, `SuiteSelection`, and `select_suite`; existing `DiscoveryResult`, `load_suite`, and `run_suite`.
- Produces: `BatchResult.selection_active: bool`, `BatchResult.selected_cases: int`, `BatchResult.filtered_out_cases: int`, and `run_batch(discovery: DiscoveryResult, show_server_logs: bool = False, selection: SelectionFilter | None = None) -> BatchResult`.

- [ ] **Step 1: Write failing batch selection tests**

Add tests named:

- `test_batch_filters_before_running_and_aggregates_selection_counts` — two loaded suites, one partly selected and one fully filtered out; assert only the partly selected suite reaches `run_suite`, its filtered suite contains only the matching cases, and aggregate counts use all loaded cases;
- `test_batch_does_not_run_any_suite_when_selection_matches_nothing` — assert no runner call, no `SuiteRun`, zero selected, and the full filtered-out count;
- `test_batch_still_reports_load_errors_when_other_cases_are_selected` — one malformed suite plus one selected valid suite; assert both the configuration error and valid result remain;
- `test_filtered_cases_are_not_runtime_skips_after_selected_infrastructure_error` — run a selected suite result containing one error and later selected skips while other original cases were filtered; assert batch skip counts include only the runner-produced selected skips.

Also extend the existing no-filter sequential test to assert `selection_active is False`, `selected_cases` equals the number of loaded cases, `filtered_out_cases == 0`, and every original case reaches the runner.

- [ ] **Step 2: Run batch tests and verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_batch.py -q`

Expected: FAIL because `run_batch` has no selection input or aggregate counters.

- [ ] **Step 3: Integrate selection into batch execution**

Give the new `BatchResult` fields defaults so existing constructors remain valid. In `run_batch`, normalize `None` to an inactive `SelectionFilter`, load every suite, call `select_suite`, accumulate counts, skip `run_suite` and `SuiteRun` creation when the selected suite has no cases, and preserve the current configuration/execution exception boundaries. With no active filter, execute the complete suite exactly as before.

- [ ] **Step 4: Run batch and runner tests and verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_batch.py tests/test_runner.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/mcp_rig/batch.py tests/test_batch.py
git commit -m "feat: filter cases before batch execution"
```

### Task 3: Selection Reporting and JUnit Boundaries

**Files:**
- Modify: `src/mcp_rig/report.py`
- Modify: `tests/test_report.py`
- Modify if required by RED tests: `src/mcp_rig/junit.py`
- Modify: `tests/test_junit.py`

**Interfaces:**
- Consumes: Task 2 `BatchResult` selection fields and existing `SuiteRun`/`SuiteResult` structures.
- Produces: filtered `render_batch(result: BatchResult, color: bool = False) -> str` output with `Selection: N selected, M filtered out` immediately before the existing summary, plus valid selected-only and empty batch JUnit documents.

- [ ] **Step 1: Write failing report tests**

Add tests for a filtered single-suite result and a filtered multi-suite result. Assert the exact literal `Selection: 3 selected, 7 filtered out` occurs immediately before the existing execution summary. Add a zero-selected filtered result and assert it renders `Selection: 0 selected, 4 filtered out` without a fake suite heading. Retain or add an exact no-filter assertion proving no `Selection:` line is introduced.

- [ ] **Step 2: Run report tests and verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_report.py -q`

Expected: FAIL because reporting does not know about selection totals.

- [ ] **Step 3: Implement conditional selection rendering**

Keep `render_suite`'s default output unchanged. Add a focused helper for the selection line, and have `render_batch` insert it only when `result.selection_active` is true. For a filtered single suite, render the existing suite body and place the global selection line before its final execution summary; for multi/zero-suite batches, place it before the aggregate `Suites:`/`Cases:` summary.

- [ ] **Step 4: Run report tests and verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_report.py -q`

Expected: all report tests pass.

- [ ] **Step 5: Write or extend JUnit boundary tests**

Add tests proving:

- filtered-out cases absent from `BatchResult.suites` do not appear in XML or root counts;
- runtime-skipped selected cases remain `<skipped>` entries;
- a filtered zero-suite `BatchResult` writes a `testsuites` root with `tests="0"`, `failures="0"`, `errors="0"`, `skipped="0"`, and `time="0.000"`;
- a zero-selected result with a configuration error retains the existing synthetic error case;
- a no-filter fixture produces the same element tree as before.

- [ ] **Step 6: Run JUnit tests and verify behavior**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_junit.py -q`

Expected: PASS if the current batch writer already satisfies the contract. If a test fails, make only the minimal change in `src/mcp_rig/junit.py`, rerun, and require all JUnit tests to pass.

- [ ] **Step 7: Run Task 3 tests together**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_report.py tests/test_junit.py -q`

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/mcp_rig/report.py src/mcp_rig/junit.py tests/test_report.py tests/test_junit.py
git commit -m "feat: report filtered test selections"
```

If `src/mcp_rig/junit.py` remains unchanged, omit it from `git add`.

### Task 4: Public CLI Filtering Contract

**Files:**
- Modify: `src/mcp_rig/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 `SelectionFilter` and `validate_tag`, Task 2 filtered `run_batch`, Task 3 conditional reporting/JUnit behavior.
- Produces: repeatable `mcp-rig run --case PATTERN`, `--tag TAG`, and `--exclude-tag TAG`; `_tag_arg(value: str) -> str`; exit code `2` and `error: filters matched no test cases` for an active global zero-match selection.

- [ ] **Step 1: Write failing CLI validation and selection tests**

Use the real public `main()` boundary and fixture MCP server to add tests for:

- exact-name and glob `--case` selection;
- repeated `--case` OR behavior;
- repeated `--tag` AND behavior with inherited suite tags;
- any-match `--exclude-tag` behavior;
- combined name/include/exclude filtering;
- duplicate CLI tags behaving as one set member;
- invalid `--tag` and `--exclude-tag` values returning exit code `2` before suite discovery;
- an include/exclude contradiction printing `error: filters matched no test cases`, returning `2`, writing requested empty JUnit, and never starting the fixture server;
- a multi-suite batch where one suite is fully filtered out and another runs;
- a mixed batch where one valid suite is selected and one malformed suite still yields a configuration error and exit code `2`;
- filtered output containing the exact `selected / filtered out` line;
- the existing unfiltered single-file stdout fixture remaining byte-for-byte identical.

Use an observable fixture-server side effect for “never starts” rather than asserting a mock call.

- [ ] **Step 2: Run focused CLI tests and verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_cli.py -q`

Expected: FAIL because the parser rejects the new options and the CLI cannot construct or interpret a selection.

- [ ] **Step 3: Add repeatable parser options and shared tag validation**

Add the three options only to the `run` subcommand. Use `action="append"` with empty-list defaults, route both tag flags through `_tag_arg`, translate `validate_tag` failures to `argparse.ArgumentTypeError`, and construct one immutable `SelectionFilter` in `_cmd_run`.

- [ ] **Step 4: Wire filters through execution and rendering**

Pass the selection value to `run_batch`. Preserve `_render_run`'s existing compatibility branch only when `result.selection_active` is false; filtered runs go through `render_batch`. After errors are rendered and output/JUnit are written, return `EXIT_USAGE` when an active selection has `selected_cases == 0`, printing the exact zero-match error once. Preserve the existing higher-level error/failure precedence for non-empty selections.

- [ ] **Step 5: Run CLI and cross-layer tests and verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_cli.py tests/test_selection.py tests/test_batch.py tests/test_report.py tests/test_junit.py -q`

Expected: all selected tests pass with no server process leak or traceback.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/mcp_rig/cli.py tests/test_cli.py
git commit -m "feat: expose case and tag filters in the CLI"
```

### Task 5: Documentation and Release-Grade Verification

**Files:**
- Modify: `README.md`
- Verify only: `pyproject.toml`, `examples/`, complete source and test tree

**Interfaces:**
- Consumes: the complete public CLI contract from Tasks 1–4.
- Produces: English user documentation and a branch verified through source tests, lint, distributions, Twine, and an installed-wheel filtered smoke run.

- [ ] **Step 1: Document tags and filtering in English**

Add a focused README section showing suite-level and case-level tags, inherited effective tags, `--case "opens*"`, repeated `--tag`, `--exclude-tag`, AND/OR semantics, the `selected / filtered out` output vocabulary, zero-match exit code `2`, and the fact that filtered-out cases are absent from JUnit rather than skipped.

- [ ] **Step 2: Run documentation-adjacent public CLI tests**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest tests/test_cli.py tests/test_spec.py -q`

Expected: all selected tests pass and the documented commands match tested syntax.

- [ ] **Step 3: Commit documentation**

```bash
git add README.md
git commit -m "docs: explain case and tag filtering"
```

- [ ] **Step 4: Run the complete source verification**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m pytest -q`

Expected: all tests pass with zero failures.

Run: `/Users/gorkem.gul/Projects/mcptest/.venv/bin/ruff check .`

Expected: `All checks passed!`

Run: `git diff --check`

Expected: no output and exit code `0`.

- [ ] **Step 5: Build and inspect distributions outside the repository**

Run from the feature worktree, directing output to a fresh temporary directory:

```bash
/Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m build --outdir /private/tmp/mcp-rig-filter-dist
/Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m twine check /private/tmp/mcp-rig-filter-dist/*
```

Expected: one wheel and one sdist build successfully, and Twine reports `PASSED` for both.

- [ ] **Step 6: Smoke-test the installed wheel with real filtering**

Create a fresh virtual environment under `/private/tmp`, install the built wheel, and create a temporary fixture-backed suite with inherited `playwright`, case-local `smoke`, and an excluded `slow` case. Run the installed `mcp-rig` executable with `--tag playwright --tag smoke --exclude-tag slow --junit <temp-path>`. Assert the command exits `0`, exactly the intended case runs, stdout contains literal selected/filtered-out counts, and the JUnit root contains exactly one test.

- [ ] **Step 7: Record final verification without creating a verification-only commit**

Confirm `git status --short` is clean. Record the exact pytest count, Ruff result, build artifacts, Twine result, and wheel-smoke result in the execution ledger and final handoff. Do not create a commit when no tracked files changed.

---

## Completion Criteria

- All five task commits are present with professional messages and no assistant signature or co-author trailer.
- The full test suite and Ruff pass on the feature branch.
- Wheel and sdist pass Twine checks.
- A clean virtual environment runs the installed wheel with combined case/tag filters and produces the expected JUnit count.
- A final whole-branch review finds no unresolved critical or important issues.
- The branch is ready for the previously chosen push, pull-request, CI, merge, and post-merge verification workflow.
