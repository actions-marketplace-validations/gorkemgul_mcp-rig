"""Run suite cases sequentially against one MCP server process."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_rig.assertions import check
from mcp_rig.client import CallOutcome, Probe, connect
from mcp_rig.spec import Case, Suite


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    failures: list[str]
    outcome: CallOutcome


@dataclass(frozen=True)
class SuiteResult:
    results: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(item.passed for item in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0


async def run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult:
    results: list[CaseResult] = []
    async with connect(suite.server, show_server_logs=show_server_logs) as probe:
        for case in suite.cases:
            results.append(await _run_case(probe, case))
    return SuiteResult(results)


async def _run_case(probe: Probe, case: Case) -> CaseResult:
    outcome = await probe.call(case.call, case.args)
    failures = check(case.expect, outcome)
    return CaseResult(
        name=case.name,
        passed=not failures,
        failures=failures,
        outcome=outcome,
    )
