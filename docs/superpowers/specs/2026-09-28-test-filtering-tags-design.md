# Test Filtering and Tags Design

**Date:** 2026-09-28
**Status:** Approved for implementation planning

## Context

MCP Rig can discover and execute one or more YAML suites as a resilient batch,
but every declared test case currently runs. Real MCP server suites need a
deterministic way to select a focused subset for local development and CI
without duplicating suite files.

This increment adds suite and case tags, case-name filtering, tag inclusion,
and tag exclusion. Selection happens after a suite has been parsed and
validated but before its MCP server process starts. The feature must preserve
all existing behavior when no filters are supplied.

Snapshots, arbitrary boolean tag expressions, suite-path filtering, regular
expressions, and persisted filter profiles are outside this increment.

## Goals

- Let suite authors attach reusable tags at suite and case scope.
- Let CLI users select cases by name pattern and effective tags.
- Avoid starting an MCP server for a suite with no selected cases.
- Distinguish cases removed by selection from cases skipped during execution.
- Keep console, exit-code, and JUnit behavior unchanged when filters are absent.
- Make the selection engine independent from MCP process execution.

## User-Facing Configuration

Suites may define an optional top-level `tags` list and each test case may
define its own optional `tags` list:

```yaml
server: npx @playwright/mcp@latest
tags: [playwright]

tests:
  - name: opens homepage
    tags: [smoke, browser]
    call: browser_navigate
    args:
      url: https://example.com
```

A case's effective tags are the set union of the suite tags and that case's
tags. In the example, `opens homepage` has the effective tags `playwright`,
`smoke`, and `browser`.

### Tag validation

Every tag must be a non-empty string matching:

```text
[a-z0-9][a-z0-9_-]*
```

Tags are therefore lowercase and contain only ASCII lowercase letters, digits,
hyphens, and underscores. Duplicate tags use set semantics and are retained
only once. An invalid `tags` value or invalid tag is a suite configuration
error reported through the existing `SpecError` path.

Both suite and case tags default to an empty set. Tags are metadata only; they
do not affect execution unless the user supplies a filter.

## Command-Line Interface

The `run` command gains three repeatable options:

```text
--case PATTERN
--tag TAG
--exclude-tag TAG
```

Examples:

```bash
mcp-rig run suites/ --case "opens*"
mcp-rig run suites/ --tag playwright --tag smoke
mcp-rig run suites/ --exclude-tag slow
mcp-rig run suites/ --case "opens*" --tag smoke --exclude-tag flaky
```

`--case` uses case-sensitive shell-style glob matching against the complete
case `name`. Multiple `--case` options use OR semantics: a case passes the name
criterion when any supplied pattern matches.

Multiple `--tag` options use AND semantics: a case must contain every requested
tag in its effective tag set. Multiple `--exclude-tag` options use OR semantics:
a case is removed when its effective tag set contains any excluded tag.

The three filter dimensions combine with AND semantics. A case is selected
only when:

1. its name matches at least one `--case` pattern, or no name patterns were
   supplied;
2. its effective tags contain every `--tag`, or no included tags were supplied;
3. its effective tags contain none of the `--exclude-tag` values.

CLI tag values use the same validation rule as YAML tags. Invalid CLI tags are
usage errors and produce exit code `2` before suite discovery or server startup.
An include/exclude contradiction is allowed and naturally produces no matches.

This increment deliberately does not add `--exclude-case`. Tag exclusion covers
the primary exclusion use case without expanding the name-filter grammar.

## Architecture

Selection is a separate pure layer between configuration loading and execution.
It does not belong in the runner and does not inspect raw YAML.

### Specification model

`mcp_rig.spec.Suite` and `mcp_rig.spec.Case` gain immutable tag collections.
The parser validates and canonicalizes the declared lists. The suite retains
its own tags, while effective tag union is computed by the selection layer so
the distinction between inherited and case-local metadata remains explicit.

### Selection model

A new `mcp_rig.selection` module owns:

- an immutable filter value containing case patterns, required tags, and
  excluded tags;
- tag validation shared by YAML parsing and CLI validation;
- deterministic case matching using `fnmatch.fnmatchcase` semantics;
- a pure operation that returns a suite containing only selected cases plus
  selection counts.

The selector preserves original suite order and original case order. It never
mutates a loaded suite and never starts or contacts an MCP server.

### Batch integration

`run_batch` accepts the optional filter value. For every discovered suite it:

1. loads and validates the complete suite;
2. applies the selector;
3. accumulates selected and filtered-out case counts;
4. omits execution for a suite with zero selected cases;
5. passes a non-empty selected suite to the existing runner.

Every discovered suite is still parsed and validated even when its cases would
not match. Filters must not hide malformed configuration. Discovery,
configuration, and execution errors retain their current isolation and exit
precedence.

Suites with no selected cases do not create an empty `SuiteRun`, do not start a
server, and do not print an empty suite heading. Selection totals remain
available on the aggregate batch result.

### Runner isolation

`run_suite` continues to execute every case it receives and remains unaware of
filters. This preserves its lifecycle contract: it starts one process for one
non-empty suite, runs cases sequentially, and classifies execution skips only
after infrastructure failures.

Cases removed by selection are not represented as `CaseStatus.SKIPPED`.
`skipped` continues to mean that a selected case could not run because of an
execution condition.

## Reporting

When any filter option is active, terminal output adds a selection line before
the existing execution summary:

```text
Selection: 3 selected, 7 filtered out
Summary: 3 passed, 0 failed, 0 errors, 0 skipped
```

The normal per-case and per-suite rendering includes only executed, selected
cases. The aggregate selection counts cover every successfully parsed suite,
including suites for which all cases were filtered out.

When filters select zero cases globally:

- no MCP server process is started;
- stderr contains `error: filters matched no test cases`;
- the command returns exit code `2`;
- configuration or discovery errors are still rendered;
- if `--junit` was requested, a valid empty JUnit report is written.

If at least one case is selected, existing result-based exit precedence remains:

- `0` when selected cases pass and there are no errors;
- `1` when selected cases have assertion failures and there are no errors;
- `2` for discovery, configuration, infrastructure, report-writing, or usage
  errors.

When no filters are active, terminal output remains byte-for-byte compatible
with the existing single-suite and batch behavior. No selection line is added.

## JUnit XML

JUnit contains only selected cases that were actually passed to execution.
Filtered-out cases are absent rather than marked skipped. This keeps JUnit test
counts aligned with the executed workload and avoids conflating selection with
runtime inability to execute.

When no cases match, no discovery or configuration errors occurred, and
`--junit` is requested, MCP Rig writes a valid `testsuites` document with zero
tests, failures, errors, and skipped cases, then returns exit code `2`. Writing
the empty report prevents CI consumers from failing with a secondary
missing-report error. If discovery or configuration errors also exist, their
existing synthetic JUnit error cases remain present.

JUnit output without filters remains unchanged.

## Error Handling

- Invalid YAML tag containers or values raise `SpecError` with the existing
  suite path and case location context.
- Invalid CLI tag values are rejected by the CLI before discovery.
- Glob patterns are treated as shell-style patterns, not regular expressions;
  they do not have a separate compilation-error path.
- A zero-match filter is a usage/selection error, not a passing empty run.
- Filtered-out suites cannot produce setup or teardown errors because their
  servers are never started.
- `KeyboardInterrupt` and other `BaseException` subclasses retain the current
  propagation behavior.

## Compatibility

Existing suite files require no changes because both tag fields are optional.
Existing calls to `run_suite` continue to work unchanged. Existing calls to
`run_batch` remain valid through a default no-filter argument. Existing CLI
commands produce the same execution, rendering, JUnit, and exit codes when no
filter flags are supplied.

The public vocabulary uses `filtered out`, not `deselected`, and does not count
filtered-out cases as skipped.

## Testing Strategy

Tests will cover:

- suite and case tag defaults, parsing, duplicate handling, and validation;
- effective suite-to-case tag inheritance;
- case-sensitive glob matching and OR behavior across repeated `--case` values;
- AND behavior across repeated `--tag` values;
- exclusion when any `--exclude-tag` matches;
- AND composition across name, included-tag, and excluded-tag dimensions;
- stable suite and case ordering after selection;
- zero-selected suites never invoking the runner or opening an MCP connection;
- selection totals across single-suite and multi-suite batches;
- all-zero selection reporting, empty JUnit output, and exit code `2`;
- configuration errors remaining visible even when filters remove all valid
  cases;
- JUnit containing selected cases only;
- exact no-filter terminal compatibility for successful single-file execution;
- unchanged no-filter batch and JUnit behavior;
- CLI validation of invalid included and excluded tags.

All behavior changes will be developed through failing public-behavior tests.
The complete test suite, Ruff, distribution build, Twine checks, and installed
wheel smoke tests remain release gates.

## Out of Scope

- `--exclude-case`;
- regular-expression or substring name modes;
- arbitrary boolean tag expressions such as `smoke or regression`;
- filtering suite file paths or suite names;
- implicit tags derived from directories or filenames;
- persisted filter profiles or configuration files;
- parallel execution;
- snapshots or snapshot updates.

Those capabilities can be added later without moving selection into the runner
or changing the tag inheritance model.
