from pathlib import Path

import pytest

from mcp_rig.client import ServerSpec
from mcp_rig.selection import (
    SelectionFilter,
    select_suite,
    validate_tag,
)
from mcp_rig.spec import Case, Suite


def make_suite(*cases: Case, tags: frozenset[str] = frozenset()) -> Suite:
    return Suite(
        path=Path("suite.yaml"),
        server=ServerSpec("unused"),
        cases=list(cases),
        tags=tags,
    )


@pytest.mark.parametrize("value", ["smoke", "browser-tools", "ci_fast"])
def test_validate_tag_accepts_canonical_values(value):
    assert validate_tag(value) == value


@pytest.mark.parametrize("value", ["Smoke", "browser tools", "", 3, "-slow"])
def test_validate_tag_rejects_noncanonical_values(value):
    with pytest.raises(ValueError, match=r"\[a-z0-9\]"):
        validate_tag(value)


def test_inherits_suite_tags_without_mutating_case_tags():
    case = Case("opens homepage", "browser_navigate", tags=frozenset({"smoke"}))
    suite = make_suite(case, tags=frozenset({"playwright"}))

    result = select_suite(
        suite,
        SelectionFilter(required_tags=frozenset({"playwright", "smoke"})),
    )

    assert result.suite.cases == [case]
    assert case.tags == frozenset({"smoke"})


def test_case_patterns_are_case_sensitive_and_use_or_semantics():
    opens = Case("opens homepage", "one")
    capitalized = Case("Opens admin", "two")
    health = Case("health check", "three")

    result = select_suite(
        make_suite(opens, capitalized, health),
        SelectionFilter(case_patterns=("opens*", "*check")),
    )

    assert result.suite.cases == [opens, health]


def test_required_tags_use_and_semantics():
    smoke = Case("smoke", "one", tags=frozenset({"smoke"}))
    regression = Case("regression", "two", tags=frozenset({"regression"}))

    result = select_suite(
        make_suite(smoke, regression, tags=frozenset({"playwright"})),
        SelectionFilter(required_tags=frozenset({"playwright", "smoke"})),
    )

    assert result.suite.cases == [smoke]


def test_any_excluded_tag_filters_a_case():
    stable = Case("stable", "one", tags=frozenset({"smoke"}))
    slow = Case("slow", "two", tags=frozenset({"slow"}))
    flaky = Case("flaky", "three", tags=frozenset({"flaky"}))

    result = select_suite(
        make_suite(stable, slow, flaky),
        SelectionFilter(excluded_tags=frozenset({"slow", "flaky"})),
    )

    assert result.suite.cases == [stable]


def test_filter_dimensions_compose_and_preserve_declaration_order():
    first = Case("opens homepage", "one", tags=frozenset({"smoke"}))
    wrong_name = Case("takes screenshot", "two", tags=frozenset({"smoke"}))
    excluded = Case(
        "opens admin",
        "three",
        tags=frozenset({"smoke", "flaky"}),
    )
    last = Case("opens profile", "four", tags=frozenset({"smoke"}))

    result = select_suite(
        make_suite(first, wrong_name, excluded, last, tags=frozenset({"playwright"})),
        SelectionFilter(
            case_patterns=("opens*",),
            required_tags=frozenset({"playwright", "smoke"}),
            excluded_tags=frozenset({"flaky"}),
        ),
    )

    assert result.suite.cases == [first, last]
    assert (result.selected, result.filtered_out) == (2, 2)


def test_no_filters_return_an_equivalent_suite():
    suite = make_suite(Case("one", "echo"), Case("two", "echo"))
    filters = SelectionFilter()

    result = select_suite(suite, filters)

    assert filters.active is False
    assert result.suite == suite
    assert (result.selected, result.filtered_out) == (2, 0)


def test_same_included_and_excluded_tag_selects_nothing():
    suite = make_suite(Case("one", "echo", tags=frozenset({"smoke"})))

    result = select_suite(
        suite,
        SelectionFilter(
            required_tags=frozenset({"smoke"}),
            excluded_tags=frozenset({"smoke"}),
        ),
    )

    assert result.suite.cases == []
    assert (result.selected, result.filtered_out) == (0, 1)
