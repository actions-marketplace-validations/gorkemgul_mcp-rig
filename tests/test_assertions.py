from mcp_rig.assertions import check
from mcp_rig.client import CallOutcome


def outcome(text="", is_error=False, structured=None, latency_ms=10.0):
    return CallOutcome(is_error=is_error, text=text, structured=structured, latency_ms=latency_ms)


def test_empty_expect_requires_success():
    assert check({}, outcome("ok")) == []
    assert check({}, outcome("boom", is_error=True)) == [
        "is_error: expected False, got True (text: 'boom')"
    ]


def test_explicit_error_expectation():
    assert check({"is_error": True}, outcome("boom", is_error=True)) == []
    assert check({"is_error": True}, outcome("ok")) == [
        "is_error: expected True, got False (text: 'ok')"
    ]


def test_contains_accepts_one_string():
    assert check({"contains": "Ada"}, outcome("Hello Ada")) == []
    assert check({"contains": "Ada"}, outcome("Hello Lin")) == [
        "contains: 'Ada' not found in 'Hello Lin'"
    ]


def test_contains_requires_every_string_in_a_list():
    assert check({"contains": ["21", "sunny"]}, outcome("21°C and sunny")) == []
    assert check({"contains": ["21", "rain"]}, outcome("21°C and sunny")) == [
        "contains: 'rain' not found in '21°C and sunny'"
    ]


def test_not_contains_accepts_one_string_or_a_list():
    assert check({"not_contains": "null"}, outcome("Weather: null")) == [
        "not_contains: 'null' found in 'Weather: null'"
    ]
    assert check({"not_contains": ["password", "secret"]}, outcome("password and secret")) == [
        "not_contains: 'password' found in 'password and secret'",
        "not_contains: 'secret' found in 'password and secret'",
    ]


def test_matches_uses_regex_search():
    assert check({"matches": r"\d+°C"}, outcome("now 21°C")) == []
    assert check({"matches": r"^\d+$"}, outcome("now 21")) == [
        "matches: /^\\d+$/ did not match 'now 21'"
    ]


def test_max_latency_includes_the_boundary():
    assert check({"max_latency_ms": 100}, outcome(latency_ms=100)) == []
    assert check({"max_latency_ms": 100}, outcome(latency_ms=250)) == [
        "max_latency_ms: took 250 ms, limit 100 ms"
    ]


def test_advanced_text_failures_follow_fixed_order():
    failures = check(
        {
            "max_latency_ms": 1,
            "matches": r"^x$",
            "not_contains": "bad",
            "contains": "good",
            "is_error": True,
        },
        outcome("bad", latency_ms=2),
    )

    assert failures == [
        "is_error: expected True, got False (text: 'bad')",
        "contains: 'good' not found in 'bad'",
        "not_contains: 'bad' found in 'bad'",
        "matches: /^x$/ did not match 'bad'",
        "max_latency_ms: took 2 ms, limit 1 ms",
    ]


def test_json_path_reads_text_json_and_list_indexes():
    text_outcome = outcome('{"user": {"name": "Ada", "roles": ["admin"]}}')

    assert check({"json_path": {"user.name": "Ada", "user.roles.0": "admin"}}, text_outcome) == []
    assert check({"json_path": {"user.age": 3}}, text_outcome) == ["json_path user.age: missing"]
    assert check({"json_path": {"user.name": "Bob"}}, text_outcome) == [
        "json_path user.name: expected 'Bob', got 'Ada'"
    ]


def test_json_path_prefers_structured_content_including_falsey_values():
    assert check({"json_path": {"result": 5}}, outcome("not json", structured={"result": 5})) == []
    assert check(
        {"json_path": {"flag": False}},
        outcome('{"flag": true}', structured={"flag": False}),
    ) == []
    assert check({"json_path": {"value": None}}, outcome('{"value": null}')) == []


def test_json_path_rejects_invalid_list_indexes_without_raising():
    response = outcome('{"items": ["first"]}')

    assert check(
        {"json_path": {"items.-1": "first", "items.one": "first", "items.2": "first"}},
        response,
    ) == [
        "json_path items.-1: missing",
        "json_path items.one: missing",
        "json_path items.2: missing",
    ]


def test_json_expectations_report_one_failure_for_non_json_text():
    expect = {"json_path": {"a": 1}, "schema": {"type": "object"}}

    assert check(expect, outcome("hello")) == ["json: response is not JSON: 'hello'"]


def test_schema_validates_response_payload():
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "integer"}},
    }

    assert check({"schema": schema}, outcome('{"id": 1}')) == []
    assert check({"schema": schema}, outcome('{"id": "x"}')) == [
        "schema: 'x' is not of type 'integer'"
    ]


def test_schema_returns_multiple_errors_in_deterministic_order():
    schema = {
        "type": "object",
        "properties": {
            "b": {"type": "string"},
            "a": {"type": "integer"},
        },
    }

    assert check({"schema": schema}, outcome(structured={"b": 0, "a": "x"})) == [
        "schema: 'x' is not of type 'integer'",
        "schema: 0 is not of type 'string'",
    ]


def test_reports_every_failed_expectation():
    failures = check({"is_error": True, "contains": ["Ada", "admin"]}, outcome("Lin"))
    assert failures == [
        "is_error: expected True, got False (text: 'Lin')",
        "contains: 'Ada' not found in 'Lin'",
        "contains: 'admin' not found in 'Lin'",
    ]


def test_long_text_is_shortened_in_failure_messages():
    [failure] = check({"contains": "missing"}, outcome("a" * 200))
    assert "…" in failure
    assert len(failure) < 150
