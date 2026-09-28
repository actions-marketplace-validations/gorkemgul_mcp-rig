# Snapshot Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, deterministic, file-backed snapshot assertions and an explicit `--update-snapshots` workflow to `mcp-rig run`.

**Architecture:** A focused `mcp_rig.snapshots` module owns sidecar paths, strict YAML parsing, outcome normalization, comparison, staged updates, and atomic persistence. Suite parsing and discovery validate the snapshot contract; batch execution owns each snapshot session; the runner only turns snapshot comparisons into ordinary case failures. CLI, terminal, and JUnit layers consume structured batch results without reconstructing snapshot state.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, tempfile/os.replace, PyYAML, pytest, Ruff, Hatchling/build, Twine

**Spec:** `docs/superpowers/specs/2026-09-28-snapshot-testing-design.md`

## Global Constraints

- Support only local stdio MCP tool suites; do not add resources, prompts, remote transports, or parallel execution.
- `snapshot` accepts only the boolean value `true` and composes with all existing expectations.
- Ordinary runs never create, update, or delete snapshot files.
- Snapshot differences are assertion failures with exit code `1`; snapshot configuration, serialization, and I/O errors produce exit code `2`.
- Store `is_error` plus structured content when present, otherwise exact text; never store latency or protocol error codes.
- Use `<suite-stem>.snap.yaml`, version `1`, strict schema validation, deterministic rendering, and atomic replacement.
- Filtered updates preserve unselected and unknown entries; only complete unfiltered suites may prune stale entries.
- Preserve byte-for-byte terminal behavior for runs that neither use snapshot updates nor produce snapshot failures.
- Keep public naming in English and do not add assistant signatures or co-author trailers to commits.

## Review Focus

- A YAML boolean `version: true` must not pass as integer version `1`; Task 2 pins strict type validation.
- A suite reached through a symlink must resolve to one canonical sidecar rather than creating an alias-specific file; Task 1 pins canonical path derivation.
- Non-ASCII text and embedded CRLF characters must survive a write/read cycle exactly; Task 2 pins round-trip equality.
- A sidecar read `OSError` must become a suite-local snapshot error while later suites still run; Task 3 pins batch isolation.
- A failed atomic replace must preserve the previous sidecar and remove the temporary sibling; Task 2 pins failure cleanup.

---

### Task 1: Snapshot Suite Contract and Discovery

**Files:**
- Create: `src/mcp_rig/snapshots.py`
- Modify: `src/mcp_rig/spec.py`
- Modify: `src/mcp_rig/discovery.py`
- Create: `tests/test_snapshots.py`
- Modify: `tests/test_spec.py`
- Modify: `tests/test_discovery.py`

**Interfaces:**
- Consumes: existing `Case.expect`, `Suite.path`, `SpecError`, `DiscoveryResult`, and `.yaml`/`.yml` discovery behavior.
- Produces: `SnapshotError(ValueError)`, `is_snapshot_sidecar(path: str | Path) -> bool`, and `snapshot_path(suite_path: str | Path) -> Path`; validated `expect["snapshot"] is True`; unique names among snapshot-enabled cases; reserved-sidecar discovery behavior.

- [ ] **Step 1: Write failing path and discovery tests**

Add tests with these exact behaviors:

```python
def test_snapshot_path_is_canonical_and_replaces_suite_suffix(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite", encoding="utf-8")
    alias = tmp_path / "alias.yml"
    alias.symlink_to(suite)
    assert snapshot_path(suite) == tmp_path / "suite.snap.yaml"
    assert snapshot_path(alias) == tmp_path / "suite.snap.yaml"


def test_snapshot_path_rejects_yaml_yml_stem_collision(tmp_path):
    yaml_path = tmp_path / "suite.yaml"
    yml_path = tmp_path / "suite.yml"
    yaml_path.write_text("suite", encoding="utf-8")
    yml_path.write_text("suite", encoding="utf-8")
    with pytest.raises(SnapshotError, match="same snapshot sidecar"):
        snapshot_path(yaml_path)


def test_discovery_ignores_sidecars_but_rejects_explicit_sidecar_target(tmp_path):
    suite = tmp_path / "suite.yaml"
    sidecar = tmp_path / "suite.snap.yaml"
    suite.write_text("suite", encoding="utf-8")
    sidecar.write_text("version: 1\nsnapshots: {}\n", encoding="utf-8")
    assert discover_suites([tmp_path]).paths == [suite.resolve()]
    explicit = discover_suites([sidecar])
    assert explicit.paths == []
    assert "snapshot sidecar" in explicit.errors[0].message
```

- [ ] **Step 2: Run path and discovery tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py tests/test_discovery.py -q -p no:cacheprovider`

Expected: FAIL because `mcp_rig.snapshots` and reserved-sidecar handling do not exist.

- [ ] **Step 3: Implement the sidecar path contract**

In `mcp_rig.snapshots`, define:

```python
SNAPSHOT_SUFFIX = ".snap.yaml"

class SnapshotError(ValueError): ...

def is_snapshot_sidecar(path: str | Path) -> bool: ...
def snapshot_path(suite_path: str | Path) -> Path: ...
```

Resolve the suite path before replacing its suffix. Reject unsupported suite suffixes and a sibling `.yaml`/`.yml` stem collision. Update discovery so recursive targets skip sidecars and an explicit sidecar target produces a `ValueError`-backed `DiscoveryError` containing `snapshot sidecar is not a suite`.

- [ ] **Step 4: Run path and discovery tests to verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py tests/test_discovery.py -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 5: Write failing suite-validation tests**

Extend `tests/test_spec.py` so public `load_suite` proves:

```python
def test_accepts_snapshot_true_with_other_expectations(tmp_path):
    suite = load_suite(write_suite(tmp_path, SNAPSHOT_AND_CONTAINS_YAML))
    assert suite.cases[0].expect == {"snapshot": True, "contains": "Ada"}


@pytest.mark.parametrize("value", ["false", "null", "1", "'true'", "{}", "[]"])
def test_rejects_snapshot_values_other_than_boolean_true(tmp_path, value):
    with pytest.raises(SpecError, match=r"tests\[0\].*'snapshot' must be true"):
        load_suite(write_suite(tmp_path, suite_with_snapshot(value)))


def test_rejects_duplicate_snapshot_case_names(tmp_path):
    with pytest.raises(SpecError, match="duplicate snapshot case name 'same'"):
        load_suite(write_suite(tmp_path, DUPLICATE_SNAPSHOT_NAMES_YAML))
```

Also prove duplicate names remain accepted when at most one duplicate uses a snapshot, and a suite with a stem-colliding sibling reports `SpecError` with its suite path.

- [ ] **Step 6: Run suite-validation tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_spec.py -q -p no:cacheprovider`

Expected: FAIL because `snapshot` is unknown and uniqueness/path ownership are not validated.

- [ ] **Step 7: Implement suite validation**

Add `snapshot` to `KNOWN_EXPECT_KEYS`. In `_parse_case`, require the value to be the singleton `True`. After parsing all cases, reject duplicate names among cases whose expectation contains `snapshot: true`; for any snapshot-enabled suite, call `snapshot_path` and convert `SnapshotError` into a path-contextual `SpecError`.

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py tests/test_discovery.py tests/test_spec.py -q -p no:cacheprovider`

Expected: PASS.

```bash
git add src/mcp_rig/snapshots.py src/mcp_rig/spec.py src/mcp_rig/discovery.py tests/test_snapshots.py tests/test_spec.py tests/test_discovery.py
git commit -m "feat: validate snapshot suite configuration"
```

### Task 2: Snapshot Storage, Comparison, and Atomic Updates

**Files:**
- Modify: `src/mcp_rig/snapshots.py`
- Modify: `tests/test_snapshots.py`

**Interfaces:**
- Consumes: Task 1 `SnapshotError` and `snapshot_path`; existing `CallOutcome`.
- Produces: `SnapshotKind`, immutable `SnapshotEntry`, immutable additive `SnapshotChanges`, `snapshot_entry(outcome: CallOutcome) -> SnapshotEntry`, and `SnapshotSession.open(suite_path: Path, *, update: bool) -> SnapshotSession`, `SnapshotSession.evaluate(case_name: str, outcome: CallOutcome) -> list[str]`, `SnapshotSession.finalize(declared_names: Sequence[str], *, prune: bool) -> SnapshotChanges`.

- [ ] **Step 1: Write failing normalization and comparison tests**

Cover these literal outcomes and assertions:

```python
def test_structured_content_wins_and_mapping_keys_are_canonical(tmp_path):
    entry = snapshot_entry(
        CallOutcome(False, "ignored", {"z": 1, "nested": {"b": 2, "a": 1}}, 42),
    )
    assert entry == SnapshotEntry(
        is_error=False,
        kind=SnapshotKind.STRUCTURED,
        value={"nested": {"a": 1, "b": 2}, "z": 1},
    )


def test_missing_and_changed_snapshots_return_deterministic_failures(tmp_path):
    missing = SnapshotSession.open(tmp_path / "missing.yaml", update=False)
    assert missing.evaluate("case", text_outcome("actual")) == [
        "snapshot: missing entry for 'case'"
    ]
    changed = session_from_yaml(tmp_path, TEXT_EXPECTED_YAML)
    failure = changed.evaluate("case", text_outcome("actual"))[0]
    assert failure.startswith("snapshot: mismatch for 'case'\n--- expected\n+++ actual\n")
    assert "-  value: expected" in failure
    assert "+  value: actual" in failure
```

Also test exact equality, `is_error` changes, `structured`/`text` kind changes, exact whitespace, non-ASCII plus embedded `\r\n`, and rejection of NaN or otherwise non-JSON-compatible structured values.

- [ ] **Step 2: Run normalization tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py -q -p no:cacheprovider`

Expected: FAIL because storage models and `SnapshotSession` do not exist.

- [ ] **Step 3: Implement strict loading, normalization, and comparison**

Add:

```python
class SnapshotKind(StrEnum):
    STRUCTURED = "structured"
    TEXT = "text"

@dataclass(frozen=True)
class SnapshotEntry:
    is_error: bool
    kind: SnapshotKind
    value: Any

@dataclass(frozen=True)
class SnapshotChanges:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    def __add__(self, other: SnapshotChanges) -> SnapshotChanges: ...
```

Implement `snapshot_entry`, `SnapshotSession.open`, and `SnapshotSession.evaluate`. Safe-load the exact version-1 schema, require `type(version) is int`, reject unknown fields, canonicalize structured JSON through strict JSON serialization with sorted mapping keys, and build timestamp-free unified YAML diffs.

- [ ] **Step 4: Run normalization tests to verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py -q -p no:cacheprovider`

Expected: normalization/comparison tests PASS.

- [ ] **Step 5: Write failing persistence and update tests**

Add tests proving:

```python
def test_filtered_finalize_updates_selected_and_preserves_other_entries(tmp_path):
    session = populated_session(tmp_path, update=True)
    session.evaluate("selected", text_outcome("new"))
    changes = session.finalize(["selected", "unselected"], prune=False)
    assert changes == SnapshotChanges(updated=1)
    assert load_values(tmp_path / "suite.snap.yaml") == {
        "selected": "new",
        "unselected": "old",
    }


def test_complete_finalize_prunes_stale_entries_and_deletes_empty_file(tmp_path): ...


def test_replace_failure_preserves_original_and_removes_temporary_file(
    tmp_path, monkeypatch
):
    original = write_snapshot(tmp_path, value="old")
    monkeypatch.setattr("mcp_rig.snapshots.os.replace", raising_replace)
    with pytest.raises(SnapshotError, match="could not write"):
        updated_session(original).finalize(["case"], prune=True)
    assert original.read_text(encoding="utf-8") == ORIGINAL_TEXT
    assert list(tmp_path.glob(".*.tmp")) == []
```

Also prove ordinary mode never writes, missing update files are created only at finalize, entries follow declaration order, unchanged counts are correct, `version: true` is rejected, unknown schema fields are rejected, and a non-ASCII/CRLF text entry round-trips exactly.

- [ ] **Step 6: Run persistence tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py -q -p no:cacheprovider`

Expected: FAIL because finalize/persistence is incomplete.

- [ ] **Step 7: Implement deterministic atomic persistence**

Stage updates in memory. On `finalize`, preserve entries when `prune=False`; when `prune=True`, retain only declared snapshot names in declaration order and count removals. In update mode, write a temporary sibling, flush and `os.fsync` it, then `os.replace` the destination. Clean up the temporary file on every failure and wrap read/write/delete errors in path-contextual `SnapshotError`. Delete an existing sidecar when a pruned result is empty.

- [ ] **Step 8: Run Task 2 tests and commit**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_snapshots.py -q -p no:cacheprovider`

Expected: PASS.

```bash
git add src/mcp_rig/snapshots.py tests/test_snapshots.py
git commit -m "feat: add snapshot storage and comparison"
```

### Task 3: Runner and Batch Snapshot Lifecycle

**Files:**
- Modify: `src/mcp_rig/runner.py`
- Modify: `src/mcp_rig/batch.py`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_batch.py`

**Interfaces:**
- Consumes: Task 2 `SnapshotSession`, `SnapshotChanges`, and `SnapshotError`; Task 1 validated `Case.expect["snapshot"]`.
- Produces: `run_suite(suite: Suite, show_server_logs: bool = False, snapshots: SnapshotSession | None = None) -> SuiteResult`; `BatchFailureCategory.SNAPSHOT`; `BatchResult.snapshot_update_active`, `BatchResult.snapshot_changes`; `run_batch(..., update_snapshots: bool = False) -> BatchResult`.

- [ ] **Step 1: Write failing runner-composition tests**

Add tests around the real `_run_case`/`run_suite` behavior proving:

```python
async def test_runner_combines_existing_and_snapshot_failures(fake_probe, snapshot_session):
    result = await run_snapshot_case(
        fake_probe,
        expect={"contains": "missing", "snapshot": True},
        snapshots=snapshot_session,
    )
    assert result.status is CaseStatus.FAILED
    assert result.failures[0].startswith("contains:")
    assert result.failures[1].startswith("snapshot:")


async def test_runner_stages_snapshot_update_without_hiding_other_failure(...): ...
```

Also prove cases without `snapshot: true` do not call the session and the default `snapshots=None` path preserves existing behavior.

- [ ] **Step 2: Run runner tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_runner.py -q -p no:cacheprovider`

Expected: FAIL because the runner has no snapshot session parameter.

- [ ] **Step 3: Integrate snapshot evaluation into the runner**

Pass an optional session through `run_suite` to `_run_case`. After existing `check` failures are collected, append `snapshots.evaluate(case.name, outcome)` only for snapshot-enabled cases. Do not catch `SnapshotError` in the runner; let batch classify serialization failures as snapshot errors while the existing async context still tears down the server.

- [ ] **Step 4: Run runner tests to verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_runner.py -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 5: Write failing batch-lifecycle tests**

Add tests proving:

- a selected snapshot case opens one session and passes it to `run_suite`;
- no session is opened for a fully filtered suite or a selected suite without snapshot cases;
- filtered update finalizes with `prune=False`;
- a complete unfiltered result finalizes with `prune=True`;
- a timeout, transport error, or teardown error finalizes with `prune=False`;
- snapshot changes aggregate across suites;
- malformed/read-failing sidecars do not start that suite but later suites run;
- a monkeypatched sidecar `Path.read_text` `OSError` becomes a suite-local `SNAPSHOT` failure;
- a persistence failure retains the completed `SuiteResult`, attaches a `SNAPSHOT` failure, and does not stop later suites; and
- `KeyboardInterrupt` still propagates.

Use literal assertions such as:

```python
assert result.snapshot_update_active is True
assert result.snapshot_changes == SnapshotChanges(added=1, updated=1, unchanged=2)
assert result.suites[0].result is completed_result
assert result.suites[0].error.category is BatchFailureCategory.SNAPSHOT
assert result.suites[1].result is not None
```

- [ ] **Step 6: Run batch tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_batch.py -q -p no:cacheprovider`

Expected: FAIL because batch does not own snapshot sessions or update state.

- [ ] **Step 7: Implement batch snapshot lifecycle**

Add `SNAPSHOT` to `BatchFailureCategory` and snapshot fields to `BatchResult` with immutable/default-factory-safe values. Extend `run_batch` with `update_snapshots=False`. For each selected suite with snapshot cases, open a session before server startup, pass it to the runner, and finalize it afterward. Use `prune=not selection.active and result.errors == 0`. Preserve the `SuiteResult` when finalization fails and attach the snapshot failure to the same `SuiteRun`. Catch ordinary snapshot exceptions only; never catch `BaseException`.

- [ ] **Step 8: Run Task 3 tests and commit**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_runner.py tests/test_batch.py tests/test_snapshots.py -q -p no:cacheprovider`

Expected: PASS.

```bash
git add src/mcp_rig/runner.py src/mcp_rig/batch.py tests/test_runner.py tests/test_batch.py
git commit -m "feat: integrate snapshots with suite execution"
```

### Task 4: CLI, Terminal, and JUnit Snapshot Workflow

**Files:**
- Modify: `src/mcp_rig/cli.py`
- Modify: `src/mcp_rig/report.py`
- Modify: `src/mcp_rig/junit.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_report.py`
- Modify: `tests/test_junit.py`

**Interfaces:**
- Consumes: Task 3 `run_batch(..., update_snapshots=...)`, `BatchResult.snapshot_update_active`, `SnapshotChanges`, and a `SuiteRun` that may contain both `result` and `error`.
- Produces: public `mcp-rig run --update-snapshots`; aggregate `Snapshots: A added, U updated, N unchanged, R removed`; JUnit representation of snapshot assertion and persistence failures.

- [ ] **Step 1: Write failing report and JUnit tests**

Add exact-output tests:

```python
def test_update_report_places_snapshot_counts_before_summary():
    rendered = render_batch(snapshot_batch(changes=SnapshotChanges(1, 2, 3, 4)))
    assert "Snapshots: 1 added, 2 updated, 3 unchanged, 4 removed\nSummary:" in rendered


def test_normal_batch_without_snapshot_updates_is_byte_compatible():
    assert render_batch(existing_batch_fixture()) == EXISTING_RENDERED_TEXT


def test_junit_keeps_case_results_and_adds_snapshot_persistence_error(tmp_path):
    write_batch_junit(tmp_path / "result.xml", result_and_snapshot_error_batch())
    suite = ET.parse(tmp_path / "result.xml").getroot().find("testsuite")
    assert suite.attrib == EXPECTED_COUNTS_WITH_ONE_SYNTHETIC_ERROR
    assert suite.find("testcase[@name='[suite snapshot]']/error") is not None
```

Also prove a snapshot mismatch is an ordinary `<failure>` containing the unified diff and update mode does not create a snapshot failure.

- [ ] **Step 2: Run report/JUnit tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_report.py tests/test_junit.py -q -p no:cacheprovider`

Expected: FAIL because snapshot summaries and result-plus-error JUnit output do not exist.

- [ ] **Step 3: Implement reporting and JUnit aggregation**

Render the snapshot update line only when `snapshot_update_active` is true, after any selection line and before the existing summary. Use exact singular-independent wording from the spec. Update JUnit so a `SuiteRun` with both a real result and snapshot error appends one synthetic `[suite snapshot]` testcase to the same testsuite and updates all counts.

- [ ] **Step 4: Run report/JUnit tests to verify GREEN**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_report.py tests/test_junit.py -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 5: Write failing public CLI tests**

Using the real fixture MCP server, test this sequence:

```python
def test_snapshot_create_verify_and_mismatch_workflow(tmp_path, fixture_spec, capsys):
    suite = write_snapshot_suite(tmp_path, fixture_spec, value="first")
    sidecar = tmp_path / "suite.snap.yaml"

    assert main(["run", str(suite)]) == 1
    assert sidecar.exists() is False

    assert main(["run", str(suite), "--update-snapshots"]) == 0
    assert "Snapshots: 1 added, 0 updated, 0 unchanged, 0 removed" in capsys.readouterr().out
    assert sidecar.exists()

    assert main(["run", str(suite)]) == 0
    rewrite_snapshot_suite(suite, value="second")
    assert main(["run", str(suite), "--junit", str(tmp_path / "result.xml")]) == 1
    assert "snapshot: mismatch" in capsys.readouterr().out
```

Also prove the normal mismatch does not modify sidecar bytes; `--update-snapshots` combines with `--case`/`--tag` and preserves unselected entries; stale entries prune only after full successful execution; malformed sidecars exit `2` without traceback; write errors exit `2`; multiple suites continue; and a no-snapshot run without the update flag retains exact prior output.

- [ ] **Step 6: Run CLI tests to verify RED**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_cli.py -q -p no:cacheprovider`

Expected: FAIL because the CLI flag and end-to-end workflow do not exist.

- [ ] **Step 7: Implement the public CLI workflow**

Add `--update-snapshots` only to `run`, pass it into `run_batch`, and prevent `_render_run` from taking the legacy single-suite rendering shortcut when update reporting is active. Preserve exit precedence: `result.has_errors` before `result.has_failures`. Continue writing JUnit before returning the result-based exit code so snapshot mismatches and persistence errors are represented.

- [ ] **Step 8: Run Task 4 tests and commit**

Run: `PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest tests/test_cli.py tests/test_report.py tests/test_junit.py tests/test_batch.py -q -p no:cacheprovider`

Expected: PASS.

```bash
git add src/mcp_rig/cli.py src/mcp_rig/report.py src/mcp_rig/junit.py tests/test_cli.py tests/test_report.py tests/test_junit.py
git commit -m "feat: expose snapshot updates in the CLI"
```

### Task 5: Documentation and Distribution Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete snapshot YAML, sidecar, CLI, reporting, filtering, and exit-code contracts from Tasks 1-4.
- Produces: user-facing English snapshot instructions and release-grade verification evidence for source and installed-wheel behavior.

- [ ] **Step 1: Document snapshot testing in English**

Add a focused README section showing:

- `expect: {snapshot: true}` and composition with an existing assertion;
- the generated `<suite-stem>.snap.yaml` location;
- safe first-run failure;
- `mcp-rig run suites/ --update-snapshots`;
- committing and reviewing sidecar diffs;
- filtered update preservation and full-update pruning; and
- exit code `1` for differences versus `2` for malformed/unwritable sidecars.

- [ ] **Step 2: Run the complete source verification**

Run:

```bash
PYTHONPATH=src /Users/gorkem.gul/Projects/mcptest/.venv/bin/pytest -q -p no:cacheprovider
/Users/gorkem.gul/Projects/mcptest/.venv/bin/ruff check --no-cache .
git diff --check
```

Expected: all tests PASS, Ruff prints `All checks passed!`, and `git diff --check` prints nothing.

- [ ] **Step 3: Build and validate distributions in an isolated output directory**

Run with a fresh `mktemp -d` output directory:

```bash
/Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m build --outdir "$DIST_DIR"
/Users/gorkem.gul/Projects/mcptest/.venv/bin/python -m twine check "$DIST_DIR"/*
```

Expected: exactly one `mcp_rig-0.1.0-py3-none-any.whl` and one `mcp_rig-0.1.0.tar.gz`; Twine passes both.

- [ ] **Step 4: Smoke-test the installed wheel snapshot workflow**

Create a fresh temporary virtual environment, install only the built wheel, and generate a temporary suite whose server command uses that environment's Python with the repository's absolute `tests/fixtures/fixture_server.py` path. The suite calls `get_user`, declares `snapshot: true`, and also checks `contains: Ada`.

Run the installed `mcp-rig` executable three times:

1. ordinary run: exit `1`, missing snapshot reported, no sidecar created;
2. `--update-snapshots`: exit `0`, one snapshot added, sidecar created;
3. ordinary run: exit `0`, case passes without modifying sidecar bytes.

Then parse the sidecar with `yaml.safe_load` and assert `version == 1`, `kind == "structured"`, `is_error is False`, and the stored user payload contains `name: Ada`.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md
git commit -m "docs: explain snapshot testing"
```

- [ ] **Step 6: Run the final phase gate**

Run the full pytest suite and Ruff again from the committed tree, then verify `git status --short --branch` is clean. Build/Twine/wheel smoke evidence from Steps 3-4 must also be present before final whole-branch review.

Expected: all tests pass, Ruff is clean, distribution checks pass, installed-wheel create/update/verify succeeds, and the worktree has no uncommitted files.

---

After Task 5, create the plan review package from `git merge-base main HEAD` through `HEAD`, request one fresh whole-branch review with the Review Focus above, apply at most one TDD fix pass for Critical/Important findings, record deferred minors and rulings, then use `superpowers:finishing-a-development-branch`.
