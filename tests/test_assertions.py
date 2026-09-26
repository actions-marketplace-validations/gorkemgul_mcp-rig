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
