"""Select MCP Rig test cases without starting a server."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_rig.spec import Suite

TAG_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")


def validate_tag(value: object) -> str:
    if not isinstance(value, str) or TAG_PATTERN.fullmatch(value) is None:
        raise ValueError("must match [a-z0-9][a-z0-9_-]*")
    return value


@dataclass(frozen=True)
class SelectionFilter:
    case_patterns: tuple[str, ...] = ()
    required_tags: frozenset[str] = frozenset()
    excluded_tags: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        return bool(self.case_patterns or self.required_tags or self.excluded_tags)


@dataclass(frozen=True)
class SuiteSelection:
    suite: Suite
    selected: int
    filtered_out: int


def select_suite(suite: Suite, filters: SelectionFilter) -> SuiteSelection:
    selected_cases = []
    for case in suite.cases:
        effective_tags = suite.tags | case.tags
        name_matches = not filters.case_patterns or any(
            fnmatch.fnmatchcase(case.name, pattern)
            for pattern in filters.case_patterns
        )
        tags_match = filters.required_tags.issubset(effective_tags)
        tags_allowed = effective_tags.isdisjoint(filters.excluded_tags)
        if name_matches and tags_match and tags_allowed:
            selected_cases.append(case)

    selected = len(selected_cases)
    return SuiteSelection(
        suite=replace(suite, cases=selected_cases),
        selected=selected,
        filtered_out=len(suite.cases) - selected,
    )
