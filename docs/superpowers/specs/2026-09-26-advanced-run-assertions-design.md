# MCP Rig Advanced Run Assertions Design

## Purpose

This increment deepens the existing local `mcp-rig run` workflow without
changing its transport, process lifecycle, result model, or CLI contract. A
suite author can express negative text checks, regular-expression checks,
latency limits, structured-value comparisons, and JSON Schema validation in
the existing `expect` mapping.

The increment is the first part of completing the `run` workflow. Timeout and
infrastructure-result modeling, JUnit XML, and broader CLI hardening remain
separate reviewable increments.

## Scope

This increment includes:

- `not_contains` expectations for one string or a non-empty list of strings.
- `matches` expectations using Python regular-expression search semantics.
- `max_latency_ms` expectations against the normalized call latency.
- `json_path` expectations using dotted object keys and numeric list indexes.
- `schema` expectations using JSON Schema Draft 2020-12.
- Strict configuration validation before the MCP server starts.
- Stable, human-readable failure messages for every failed expectation.
- Documentation and a runnable example of the complete expectation set.

This increment does not include:

- Per-case timeout configuration or timeout execution behavior.
- Converting infrastructure exceptions into case results.
- JUnit XML or new CLI flags.
- The `check` command or tool-definition linting.
- Remote transports, resources, prompts, snapshots, or parallel execution.
- PyPI publication or release automation.

## User Contract

An `expect` mapping may use all seven supported keys:

```yaml
tests:
  - name: user payload is valid and fast
    call: get_user
    args: {user_id: 42}
    expect:
      is_error: false
      contains: "Ada"
      not_contains: "password"
      matches: 'user #[0-9]+'
      max_latency_ms: 500
      json_path:
        user.name: Ada
        user.roles.0: admin
      schema:
        type: object
        required: [user]
        properties:
          user:
            type: object
```

An omitted or empty `expect` still means that the tool call must succeed.
Existing `is_error` and `contains` behavior remains backward compatible.

## Validation Rules

The complete suite is validated before `connect()` is called.

- The recognized expectation keys are `is_error`, `contains`,
  `not_contains`, `matches`, `max_latency_ms`, `json_path`, and `schema`.
- Unknown keys remain configuration errors.
- `not_contains` must be a string or a non-empty list containing only strings.
- `matches` must be a string that compiles as a Python regular expression.
- `max_latency_ms` must be a positive integer or floating-point number. Boolean
  values are rejected even though Python treats booleans as integers.
- `json_path` must be a non-empty mapping whose keys are non-empty strings.
  Expected values may be any YAML value so suites can compare strings,
  numbers, booleans, nulls, objects, and arrays exactly.
- `schema` must be a mapping and must itself be a valid Draft 2020-12 schema.
- Invalid regular expressions and schemas raise `SpecError` with the case
  location and concise validation detail.

Like the existing `contains` contract, an individual text expectation may be
an empty string. This increment does not silently tighten established input
semantics.

## Assertion Semantics

`check(expect, outcome)` remains a pure function returning all failure
messages. It does not raise for configuration errors because the parser has
already validated the suite.

Checks run in a fixed order independent of YAML key order:

1. `is_error`
2. `contains`
3. `not_contains`
4. `matches`
5. `max_latency_ms`
6. `json_path`
7. `schema`

### Text and regex

- Every `contains` value must occur in `CallOutcome.text`.
- Every `not_contains` value must be absent from `CallOutcome.text`; each
  present forbidden value produces a separate failure.
- `matches` uses `re.search`, so matching any substring passes. It does not
  imply whole-string matching.
- Failure messages reuse the existing 80-character response-text shortening.

### Latency

`max_latency_ms` passes when `outcome.latency_ms` is less than or equal to the
configured limit and fails only when the measured value is greater. Messages
render measured and configured milliseconds without unnecessary decimal
noise.

### JSON payload selection

JSON-based expectations share one payload selection step:

1. Use `CallOutcome.structured` when it is not `None`.
2. Otherwise parse `CallOutcome.text` with the standard JSON decoder.
3. If parsing fails, append one `json: response is not JSON` failure and skip
   both `json_path` and `schema` checks for that outcome.

The current normalized outcome uses `None` both when structured content is
absent and when its value is JSON null. Therefore `structured is None` always
falls back to text parsing; a text response of `null` still produces a valid
JSON null payload.

### JSON path

A path such as `user.roles.0` is traversed one segment at a time:

- On a mapping, the segment is used as an exact string key.
- On a list, a non-negative decimal segment is used as the list index.
- A missing key, invalid index, out-of-range index, or incompatible container
  produces `json_path <path>: missing`.
- A resolved value is compared with the YAML expected value using Python
  equality. A mismatch reports both values with `repr`-style formatting.

Keys containing literal dots and JSONPath operators such as `$`, brackets,
wildcards, filters, or escaping are not supported in this increment. The
feature is deliberately a small dotted-path lookup, not a JSONPath language.

### JSON Schema

Schema validation uses `jsonschema.Draft202012Validator`. The suite parser
calls `check_schema` so an invalid schema is a configuration error. Assertion
evaluation reports validation failures rather than raising them.

All validation errors are collected in deterministic order by their instance
path and message. Each becomes a separate `schema: <message>` failure. This
keeps the existing promise that one case reports all of its assertion
failures, including multiple independent schema violations.

## Architecture and Data Flow

The existing boundaries remain intact:

```text
YAML expect mapping
        |
        v
spec.py -- validates types, regexes, and schemas before startup
        |
        v
runner.py -- obtains CallOutcome from the existing Probe
        |
        v
assertions.py -- evaluates every configured expectation
        |
        v
CaseResult.failures -> existing terminal reporter and exit-code logic
```

### `spec.py`

Expands `KNOWN_EXPECT_KEYS` and validates each new expectation. It owns all
configuration-error decisions and converts `re.error` and
`jsonschema.SchemaError` into `SpecError`.

### `assertions.py`

Keeps the public `check(expect, outcome) -> list[str]` interface. Focused
helpers handle text lists, JSON payload selection, dotted-path resolution, and
schema validation. No assertion helper performs I/O or starts a server.

### Unchanged components

`client.py`, `runner.py`, `report.py`, and `cli.py` require no behavioral
changes. Their existing normalized outcome, all-failures reporting, and exit
codes already carry the new assertion results correctly.

## Error and Exit Semantics

- Invalid assertion configuration raises `SpecError`; the CLI prints a concise
  diagnostic and returns exit code `2` before server startup.
- A valid assertion that does not match adds a case failure; the suite
  continues and the CLI returns exit code `1` after reporting all cases.
- A tool-level MCP error remains an ordinary `CallOutcome` governed by
  `is_error` and any other configured expectations.
- Infrastructure failures continue to propagate to the existing CLI boundary
  and return exit code `2`. This increment does not change their model.

## Testing Strategy

Development remains test-first.

- Parser tests cover every accepted new expectation and reject wrong types,
  empty list/mapping forms, boolean latency values, invalid regexes, and
  invalid Draft 2020-12 schemas.
- Pure assertion tests cover passing and failing text, regex, and latency
  checks; failure ordering; and accumulation of multiple failures.
- JSON tests cover structured-content preference, text fallback, JSON null,
  nested mapping traversal, list indexes, missing paths, exact-value mismatch,
  invalid response JSON, valid schemas, and multiple deterministic schema
  failures.
- A real stdio runner/CLI integration case demonstrates that the new
  expectations flow through the existing suite execution and terminal report
  without adding CLI flags.
- Existing Phase 1 and Phase 2 tests remain green.

The completion gate is the full pytest suite plus Ruff across `src` and
`tests`, followed by the installed example command.

## Success Criteria

This increment is complete when:

- All seven documented expectation keys are accepted and evaluated.
- Invalid new expectation configuration is rejected before server startup.
- JSON-based checks consistently prefer structured content and fall back to
  parsed response text.
- Dotted mapping keys and numeric list indexes resolve deterministically.
- Schema validation uses Draft 2020-12 and reports all deterministic failures.
- A case reports every failed expectation without preventing later cases.
- Existing terminal output and exit codes require no compatibility change.
- No timeout, infrastructure-result, JUnit, `check`, transport, or release
  functionality is introduced.
- Full pytest, Ruff, and the installed example command pass.
