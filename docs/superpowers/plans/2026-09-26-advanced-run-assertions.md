# MCP Rig Advanced Run Assertions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the five remaining documented `run` expectations with strict preflight validation while preserving the existing stdio workflow and CLI contract.

**Architecture:** `spec.py` validates every expectation before server startup, while the pure `assertions.py` engine evaluates normalized `CallOutcome` values in a fixed order. Existing runner, reporter, and CLI boundaries remain unchanged; one final integration task proves the new expectations flow through the installed command.

**Tech Stack:** Python 3.11+, PyYAML, `jsonschema` Draft 2020-12, pytest, Ruff, MCP Python SDK 2.x.

**Spec:** `docs/superpowers/specs/2026-09-26-advanced-run-assertions-design.md`

## Global Constraints

- Keep local stdio servers and tool calls as the only transport and MCP surface.
- Preserve `check(expect, outcome) -> list[str]`, sequential suite execution, terminal rendering, and CLI exit codes `0`, `1`, and `2`.
- Validate invalid regexes, schemas, types, and empty container forms before `connect()` is called.
- Prefer `CallOutcome.structured` when it is not `None`; otherwise parse `CallOutcome.text` as JSON.
- Do not add per-case timeout behavior, infrastructure result modeling, JUnit, `check`, remote transports, or release work.
- Use test-first development and run the complete pytest and Ruff gates before completion.

## Review Focus

- `max_latency_ms: true` must be rejected even though `bool` is a Python numeric subtype; Task 1 pins it.
- Invalid regular expressions and invalid Draft 2020-12 schemas must fail as configuration before an unstartable server is contacted; Tasks 1 and 4 pin both boundaries.
- Falsey structured values such as `False` must be used instead of falling back to unrelated response text; Task 3 pins it.
- Negative, non-numeric, and out-of-range list path segments must report a missing JSON path without raising; Task 3 pins all three.
- Multiple schema violations must be returned in deterministic instance-path/message order rather than stopping at the first error; Task 3 pins it.

---

## File Structure

- `src/mcp_rig/spec.py`: recognize and validate all seven expectation keys.
- `src/mcp_rig/assertions.py`: evaluate text, regex, latency, JSON path, and schema expectations.
- `tests/test_spec.py`: accepted and rejected expectation configuration.
- `tests/test_assertions.py`: pure assertion behavior and stable messages.
- `tests/test_cli.py`: real stdio proof and validation-before-startup boundary.
- `examples/fixture.yaml`: runnable example using advanced expectations.
- `README.md`: concise expectation reference and current scope.

### Task 1: Strict Advanced Expectation Validation

**Files:**
- Modify: `src/mcp_rig/spec.py`
- Modify: `tests/test_spec.py`

**Interfaces:**
- Consumes: existing `SpecError`, `Case`, `Suite`, and `load_suite(path)`.
- Produces: validated `Case.expect` mappings whose keys may be `is_error`, `contains`, `not_contains`, `matches`, `max_latency_ms`, `json_path`, or `schema`.

- [ ] **Step 1: Write failing acceptance tests for all new expectation shapes**

Add `test_loads_advanced_expectations` with one case containing:

```python
expect = {
    "not_contains": ["password", "secret"],
    "matches": r"user #[0-9]+",
    "max_latency_ms": 500.5,
    "json_path": {"user.name": "Ada", "user.roles.0": "admin"},
    "schema": {"type": "object", "required": ["user"]},
}
assert suite.cases[0].expect == expect
```

- [ ] **Step 2: Write failing rejection tests for invalid values**

Extend the invalid-suite table to cover:

```python
("not_contains: []", "'not_contains' must be a string or non-empty list of strings")
("not_contains: [ok, 3]", "'not_contains' must be a string or non-empty list of strings")
("matches: 3", "'matches' must be a string")
("matches: '[unclosed'", "invalid 'matches' regular expression")
("max_latency_ms: true", "'max_latency_ms' must be a positive number")
("max_latency_ms: 0", "'max_latency_ms' must be a positive number")
("json_path: {}", "'json_path' must be a non-empty mapping with non-empty string keys")
("json_path: {1: value}", "'json_path' must be a non-empty mapping with non-empty string keys")
("json_path: {'': value}", "'json_path' must be a non-empty mapping with non-empty string keys")
("schema: []", "'schema' must be a mapping")
("schema: {type: not-a-json-type}", "invalid 'schema'")
```

Construct each fragment inside a complete minimal suite so every assertion reaches the expectation validator.

- [ ] **Step 3: Run the parser tests and verify the new keys are rejected**

Run: `.venv/bin/python -m pytest tests/test_spec.py -q`

Expected: the acceptance test and new validation cases fail because only `is_error` and `contains` are recognized.

- [ ] **Step 4: Implement strict validation in `src/mcp_rig/spec.py`**

Expand `KNOWN_EXPECT_KEYS`. Add imports for `re` and `jsonschema`, then extend `_parse_case(raw, index, path) -> Case` using focused private validators or equivalent clear branches:

- `not_contains`: same string/non-empty-string-list shape as `contains`.
- `matches`: string plus `re.compile`; convert `re.error` to `SpecError`.
- `max_latency_ms`: `(int | float)`, greater than zero, explicitly excluding `bool`.
- `json_path`: non-empty dict with non-empty string keys.
- `schema`: dict plus `jsonschema.Draft202012Validator.check_schema`; convert `jsonschema.SchemaError` to `SpecError`.

Every message must include the existing case location and name prefix.

- [ ] **Step 5: Run focused and complete verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_spec.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: parser tests, the full suite, and Ruff pass.

- [ ] **Step 6: Commit the validation boundary**

```bash
git add src/mcp_rig/spec.py tests/test_spec.py
git commit -m "feat: validate advanced suite expectations"
```

### Task 2: Text, Regex, and Latency Assertions

**Files:**
- Modify: `src/mcp_rig/assertions.py`
- Modify: `tests/test_assertions.py`

**Interfaces:**
- Consumes: validated `expect: dict[str, Any]` from Task 1 and existing `CallOutcome`.
- Produces: the existing `check(expect, outcome) -> list[str]` with `not_contains`, `matches`, and `max_latency_ms` failures added in fixed order.

- [ ] **Step 1: Write failing behavior tests**

Add tests with these exact assertions:

```python
assert check({"not_contains": "null"}, outcome("Weather: null")) == [
    "not_contains: 'null' found in 'Weather: null'"
]
assert check({"not_contains": ["password", "secret"]}, outcome("password and secret")) == [
    "not_contains: 'password' found in 'password and secret'",
    "not_contains: 'secret' found in 'password and secret'",
]
assert check({"matches": r"\d+°C"}, outcome("now 21°C")) == []
assert check({"matches": r"^\d+$"}, outcome("now 21")) == [
    "matches: /^\\d+$/ did not match 'now 21'"
]
assert check({"max_latency_ms": 100}, outcome(latency_ms=100)) == []
assert check({"max_latency_ms": 100}, outcome(latency_ms=250)) == [
    "max_latency_ms: took 250 ms, limit 100 ms"
]
```

Add `test_advanced_text_failures_follow_fixed_order` using an expectation mapping inserted in a different order and assert failures still appear as `is_error`, `contains`, `not_contains`, `matches`, `max_latency_ms`.

- [ ] **Step 2: Run the assertion tests and verify the new checks are absent**

Run: `.venv/bin/python -m pytest tests/test_assertions.py -q`

Expected: failures show that `not_contains`, `matches`, and `max_latency_ms` are ignored.

- [ ] **Step 3: Extend `check(expect, outcome) -> list[str]`**

In `src/mcp_rig/assertions.py`:

- Import `re`.
- Reuse `_needles(value) -> list[str]` for `not_contains`.
- Use `re.search(expect["matches"], outcome.text)`.
- Compare `outcome.latency_ms > float(expect["max_latency_ms"])`.
- Format regex and latency messages exactly as the tests specify.
- Preserve the spec's fixed assertion order and existing 80-character shortening.

- [ ] **Step 4: Run focused and complete verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_assertions.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: assertion tests, the full suite, and Ruff pass.

- [ ] **Step 5: Commit the non-JSON assertions**

```bash
git add src/mcp_rig/assertions.py tests/test_assertions.py
git commit -m "feat: add text regex and latency assertions"
```

### Task 3: JSON Path and Draft 2020-12 Schema Assertions

**Files:**
- Modify: `src/mcp_rig/assertions.py`
- Modify: `tests/test_assertions.py`

**Interfaces:**
- Consumes: Task 2's ordered `check(expect, outcome) -> list[str]` and `CallOutcome.json() -> Any`.
- Produces: `_resolve(payload: Any, path: str) -> Any` plus JSON path and schema failures appended after non-JSON failures.

- [ ] **Step 1: Write failing payload-selection and JSON-path tests**

Add tests covering:

```python
text_outcome = outcome('{"user": {"name": "Ada", "roles": ["admin"]}}')
assert check({"json_path": {"user.name": "Ada", "user.roles.0": "admin"}}, text_outcome) == []
assert check({"json_path": {"user.age": 3}}, text_outcome) == ["json_path user.age: missing"]
assert check({"json_path": {"user.name": "Bob"}}, text_outcome) == [
    "json_path user.name: expected 'Bob', got 'Ada'"
]
assert check({"json_path": {"result": 5}}, outcome("not json", structured={"result": 5})) == []
assert check({"json_path": {"flag": False}}, outcome('{"flag": true}', structured={"flag": False})) == []
assert check({"json_path": {"value": None}}, outcome('{"value": null}')) == []
```

For a payload `{"items": ["first"]}`, assert paths `items.-1`, `items.one`, and `items.2` each return their own `json_path <path>: missing` failure without raising.

- [ ] **Step 2: Write failing JSON parse and schema tests**

Add tests proving:

```python
expect = {"json_path": {"a": 1}, "schema": {"type": "object"}}
assert check(expect, outcome("hello")) == ["json: response is not JSON: 'hello'"]

schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
assert check({"schema": schema}, outcome('{"id": 1}')) == []
assert check({"schema": schema}, outcome('{"id": "x"}')) == [
    "schema: 'x' is not of type 'integer'"
]
```

Add `test_schema_returns_multiple_errors_in_deterministic_order` with invalid values at instance paths `a` and `b`; construct the schema properties in reverse order and assert the two messages are ordered by instance path, then message.

- [ ] **Step 3: Run the assertion tests and verify JSON checks are absent**

Run: `.venv/bin/python -m pytest tests/test_assertions.py -q`

Expected: new JSON and schema tests fail because `check` does not inspect response JSON.

- [ ] **Step 4: Implement shared JSON evaluation**

In `src/mcp_rig/assertions.py`:

- Add `_MISSING = object()`.
- If either JSON expectation exists, call `outcome.json()` once; on `ValueError` append the single JSON parse failure and skip both JSON checks.
- Add `_resolve(payload: Any, path: str) -> Any`; mapping segments use exact string keys, and list segments accept only non-negative decimal indexes within range.
- Compare each `json_path` value in insertion order and append missing/mismatch messages exactly as tested.
- Instantiate `jsonschema.Draft202012Validator(expect["schema"])`, collect `iter_errors(payload)`, sort by stringified absolute-path segments and message, and append `schema: {error.message}` for every error.
- Keep JSON failures after latency failures regardless of YAML key order.

- [ ] **Step 5: Run focused and complete verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_assertions.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: assertion tests, the full suite, and Ruff pass.

- [ ] **Step 6: Commit structured assertions**

```bash
git add src/mcp_rig/assertions.py tests/test_assertions.py
git commit -m "feat: add structured response assertions"
```

### Task 4: Public Workflow Integration and Documentation

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `examples/fixture.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: validated expectations from Task 1 and the complete assertion engine from Tasks 2–3 through the unchanged `mcp_rig.cli.main(argv=None) -> int` boundary.
- Produces: an end-to-end advanced-expectation example and user-facing expectation reference; no new Python interface.

- [ ] **Step 1: Write a real-stdio CLI integration test**

Add `test_run_advanced_expectations_through_public_cli` with a suite that calls fixture `get_user` using `user_id: 1` and expects:

```yaml
is_error: false
contains: Ada
not_contains: password
matches: Ada
max_latency_ms: 5000
json_path:
  name: Ada
  roles.0: admin
schema:
  type: object
  required: [id, name, roles]
  properties:
    id: {type: integer}
    name: {type: string}
    roles: {type: array}
```

Assert `main(["run", path]) == 0`, the case has a success mark, and the summary says `1 passed, 0 failed`.

- [ ] **Step 2: Write a validation-before-startup CLI integration test**

Add `test_invalid_advanced_expectation_fails_before_server_startup` using server `/definitely/missing/mcp-rig-server` and `matches: '[unclosed'`. Assert exit `2`, stderr contains `invalid 'matches' regular expression`, and stderr does not contain `could not run server` or `Traceback`.

- [ ] **Step 3: Run the focused CLI tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`

Expected: both new tests pass against the completed Tasks 1–3, proving the pure parser and assertion behavior is connected through the public CLI and a real stdio server.

- [ ] **Step 4: Update the runnable example**

In `examples/fixture.yaml`, keep the existing cases and add a successful `get_user` case with the advanced expectation block from Step 1. Add `not_contains`, `matches`, and a generous `max_latency_ms: 5000` to an existing text case where useful. The installed example must remain deterministic and must not rely on a tight performance threshold.

- [ ] **Step 5: Update `README.md`**

Document all seven expectation keys in a compact list. State that `json_path` uses dotted mapping keys and numeric list indexes, `schema` is Draft 2020-12, structured content is preferred over text JSON, regex uses search semantics, and invalid configuration exits `2` before server startup. Keep timeout, JUnit, `check`, and PyPI listed as later increments.

- [ ] **Step 6: Run the complete product verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mcp-rig --help
.venv/bin/mcp-rig run examples/fixture.yaml
```

Expected: every command exits `0`; the full suite and Ruff pass; help still exposes only `run`; the example reports every case passed.

- [ ] **Step 7: Commit the public workflow**

```bash
git add tests/test_cli.py examples/fixture.yaml README.md
git commit -m "docs: demonstrate advanced suite assertions"
```

## Completion Review

After Task 4, compare the complete diff with `docs/superpowers/specs/2026-09-26-advanced-run-assertions-design.md` and confirm:

- All seven expectation keys are validated before server startup.
- Text, regex, latency, JSON path, and Draft 2020-12 schema checks follow the documented fixed failure order.
- Structured response content is preferred whenever it is not `None`; text JSON is the fallback.
- One invalid JSON response produces one JSON parse failure even when both JSON expectations are configured.
- Dotted mapping keys, numeric list indexes, missing paths, exact mismatches, and deterministic multiple schema violations are covered.
- The runner, reporter, CLI flags, and exit-code contract require no production changes.
- Timeout, infrastructure-result, JUnit, `check`, transport, and release work were not added.
- Full pytest, Ruff, installed help, and the runnable example all pass.

Stop after this review. Do not begin the timeout/infrastructure increment without explicit approval.
