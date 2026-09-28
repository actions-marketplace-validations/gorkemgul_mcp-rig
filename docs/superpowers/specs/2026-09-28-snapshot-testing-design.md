# Snapshot Testing Design

**Date:** 2026-09-28
**Status:** Draft for review

## Context

MCP Rig can run deterministic stdio tool suites, validate individual response
properties, execute batches, and select cases by name or tag. Those assertions
are effective when the expected property is known in advance, but they do not
provide a convenient way to review and lock down a complete tool response.

This increment adds file-backed snapshot assertions for tool outcomes. Snapshot
files are human-readable, reviewable in Git, safe in CI, and updated only by an
explicit command-line option. Existing suites and output remain unchanged when
they do not use snapshots.

## Goals

- Let a case compare its normalized tool outcome with a committed snapshot.
- Keep snapshot data beside the suite that owns it.
- Make missing and changed snapshots fail safely during ordinary runs.
- Require an explicit update option before any snapshot file is written.
- Produce stable, useful diffs in terminal and JUnit output.
- Compose snapshot assertions with existing assertions and case filters.
- Keep filesystem I/O outside the assertion engine's existing pure checks.

## User-Facing Suite Configuration

A case opts into snapshot comparison with `snapshot: true` inside `expect`:

```yaml
server: npx @playwright/mcp@latest

tests:
  - name: opens homepage
    call: browser_navigate
    args:
      url: https://example.com
    expect:
      snapshot: true
      contains: Example Domain
```

`snapshot` must be the boolean value `true`. Values such as `false`, strings,
numbers, mappings, and lists are suite configuration errors. Snapshot assertions
may be combined with every existing expectation. Updating a snapshot does not
disable or rewrite other assertions.

Case names used by snapshot-enabled cases must be unique within their suite.
Duplicate names among cases that do not use snapshots retain their existing
behavior. A duplicate snapshot name is a suite configuration error because it
would otherwise address the same persisted entry ambiguously.

## Snapshot File Location

The sidecar path replaces the suite's `.yaml` or `.yml` suffix with
`.snap.yaml`:

```text
tests/browser.yaml  -> tests/browser.snap.yaml
tests/browser.yml   -> tests/browser.snap.yaml
```

If both `browser.yaml` and `browser.yml` exist beside one another, snapshot use
in either suite is rejected because both would own the same sidecar. Renaming
one suite resolves the ambiguity.

Snapshot sidecars are not suites. Recursive discovery ignores files ending in
`.snap.yaml`. Passing a snapshot sidecar as an explicit run target produces a
target configuration error explaining that it is not a suite.

## Snapshot File Format

Snapshot files are safe-loaded YAML with a versioned top-level schema:

```yaml
version: 1
snapshots:
  opens homepage:
    is_error: false
    kind: structured
    value:
      title: Example Domain
      url: https://example.com
```

The schema is intentionally strict:

- `version` must be the integer `1`;
- `snapshots` must be a mapping;
- each key is the exact case name;
- `is_error` must be a boolean;
- `kind` must be `structured` or `text`;
- a `structured` value must be JSON-compatible; and
- a `text` value must be a string.

Unknown top-level or entry fields are rejected so misspellings cannot silently
change what is tested. An empty `snapshots` mapping is valid when read, although
a full update that leaves no entries removes the sidecar instead of writing an
empty file.

The writer emits deterministic YAML with `version` first and snapshot entries
in suite declaration order. Structured mapping keys are recursively sorted.
YAML is only the storage representation; structured equality follows JSON
value semantics rather than YAML-specific types.

## Outcome Normalization

MCP Rig derives one snapshot entry from `CallOutcome`:

1. `is_error` always records the outcome's error state.
2. When `structured` is not `None`, `kind` is `structured` and `value` is the
   canonical JSON-compatible structured result.
3. Otherwise, `kind` is `text` and `value` is the complete response text.

When an outcome contains both structured content and text, structured content
is authoritative. Latency and protocol error codes are not stored because they
are either nondeterministic or transport-specific. Text is compared exactly,
including whitespace and line endings after the Python string has been received
from the MCP client.

Non-JSON-compatible structured content cannot be snapshotted and is reported as
an execution/snapshot error rather than being coerced into an unstable string.

## Command-Line Interface

The `run` command gains one flag:

```text
--update-snapshots
```

Ordinary execution never creates, changes, or deletes snapshot files. A missing
entry or a mismatch is a normal assertion failure and therefore contributes to
exit code `1` when no higher-precedence error exists.

With `--update-snapshots`:

- a missing entry is added;
- a changed entry is replaced;
- an equal entry is counted as unchanged;
- other expectations still run and may fail; and
- only snapshot-enabled cases that produced an outcome are added or updated.

Snapshot updates are explicit but non-interactive. There is no prompt or
per-change confirmation. Users review the resulting Git diff before committing.

## Architecture

A new `mcp_rig.snapshots` module owns snapshot path resolution, strict parsing,
outcome normalization, comparison, deterministic rendering, update accounting,
and atomic persistence. It exposes structured values and errors; it does not
print output or choose process exit codes.

The suite parser recognizes and validates the `snapshot` expectation and checks
snapshot-enabled case-name uniqueness. The existing assertion engine continues
to evaluate all non-snapshot expectations without filesystem knowledge.

The batch layer owns snapshot lifecycle per suite:

1. load and validate the complete suite;
2. apply case and tag selection;
3. load the suite's snapshot sidecar when a selected case needs it;
4. create an in-memory snapshot session;
5. pass that session into the suite runner;
6. let each completed case compare or stage its normalized outcome; and
7. in update mode, finalize and atomically persist the staged suite changes.

The runner remains responsible for case status. Snapshot mismatch messages are
added to the case's assertion failures, so the case becomes `failed`, not
`error`. Snapshot loading, serialization, or persistence failures are batch
errors with exit code `2`.

No snapshot file is loaded and no snapshot session is created for a suite with
no selected snapshot-enabled cases. A fully filtered-out suite still does not
start its MCP server.

## Update and Pruning Semantics

Selection and execution state control how updates are committed:

- A filtered update changes only selected snapshot cases and preserves every
  unselected or unknown existing entry.
- An unfiltered update may remove entries whose case no longer exists or no
  longer declares `snapshot: true`.
- Pruning occurs only when the suite finishes without an infrastructure or
  teardown error. This prevents an interrupted run from deleting snapshots for
  cases it never reached.
- Completed cases may update their entries even when another ordinary assertion
  fails; the explicit update flag authorizes capturing the observed output.
- When a case has no outcome because setup, transport, or timeout handling
  prevented completion, its prior snapshot is preserved.

Changes for one suite are staged in memory and written once. The writer creates
a temporary sibling file, flushes it, and atomically replaces the destination.
If persistence fails, the original sidecar remains intact and the run reports
an exit-code-`2` error. Multiple suites update independently; a write failure in
one suite does not discard successful updates already completed for another.

## Comparison and Diff Output

Comparison covers `is_error`, `kind`, and `value` as one entry. A change from
structured to text, or from success to error, is a mismatch even if the visible
value happens to be equal.

Mismatch output uses a deterministic unified diff of the expected and actual
entry rendered as YAML. Diff headers are stable (`expected` and `actual`) and
contain no timestamps or absolute paths. Failure text begins with `snapshot:`
so terminal and JUnit consumers can identify it consistently.

The terminal displays the snapshot failure under the affected case through the
existing assertion-failure renderer. JUnit records the same failure detail in
the case's `<failure>` element. Updated snapshot assertions do not appear as
JUnit failures; unrelated assertion failures remain visible.

When `--update-snapshots` is active, terminal output adds an aggregate line
before the existing execution summary:

```text
Snapshots: 1 added, 2 updated, 3 unchanged, 1 removed
```

Selection reporting, when active, remains separate. Without the update flag,
there is no snapshot summary line. Runs with no snapshot assertions keep their
existing output byte-for-byte unless the user explicitly supplies the update
flag.

## Exit Codes and Error Handling

The existing precedence remains intact:

- `0`: all ordinary and snapshot assertions pass, with no errors;
- `1`: at least one assertion fails, including a missing or changed snapshot,
  and no higher-precedence error exists;
- `2`: discovery, suite configuration, snapshot-file schema, snapshot
  serialization, snapshot persistence, server infrastructure, JUnit writing,
  or usage fails.

Malformed sidecars include their path and the invalid field location in the
error. A missing sidecar in ordinary mode is represented as missing snapshot
assertions for its selected cases rather than a configuration error. A missing
sidecar in update mode is created only after an outcome is available.

`KeyboardInterrupt` and other `BaseException` subclasses continue to propagate.
Snapshot cleanup never swallows or transforms them.

## Compatibility

Existing suites require no changes. Existing calls to `run_suite`, `run_batch`,
the assertion engine, report renderers, and JUnit writers remain valid through
default snapshot-disabled arguments or values. Snapshot support remains limited
to the existing local stdio tool execution path.

The `.snap.yaml` discovery exclusion is narrowly scoped to the reserved sidecar
suffix. Other `.yaml` and `.yml` files retain their existing discovery behavior.

## Testing Strategy

Public-behavior tests will cover:

- strict parsing of `snapshot: true` and rejection of every other value;
- duplicate snapshot-enabled case-name rejection with suite context;
- sidecar path derivation and ambiguous `.yaml`/`.yml` sibling detection;
- discovery ignoring sidecars and rejecting explicit sidecar targets;
- structured-content precedence over text;
- recursive structured-key canonicalization;
- exact text comparison, including whitespace;
- `is_error` and `kind` changes;
- missing, equal, and changed snapshots in ordinary mode;
- concise deterministic unified diffs;
- update counts for added, updated, unchanged, and removed entries;
- composition with existing assertions;
- filtered updates preserving unselected entries;
- full successful updates pruning stale entries;
- infrastructure failures preventing unsafe pruning;
- atomic write success and failure without corrupting the old file;
- multi-suite isolation when one snapshot file fails;
- terminal, JUnit, and exit-code behavior;
- exact no-snapshot output compatibility; and
- an installed-wheel smoke test that creates and then verifies a real snapshot.

The complete pytest suite, Ruff, distribution build, Twine checks, and isolated
wheel smoke tests remain phase gates.

## Out of Scope

- inline snapshots inside suite files;
- a central snapshot directory;
- custom snapshot names or serializers;
- field masking, redaction, or ignore patterns;
- fuzzy or partial snapshot matching;
- interactive update approval;
- per-case update flags;
- snapshot support for resources, prompts, or remote transports; and
- concurrent suite execution or concurrent snapshot writers.

These may be added later without changing the sidecar version-1 comparison
contract.
