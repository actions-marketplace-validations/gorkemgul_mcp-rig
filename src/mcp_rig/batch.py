"""Run discovered MCP Rig suites sequentially as one resilient batch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mcp_rig.discovery import DiscoveryError, DiscoveryResult
from mcp_rig.runner import CaseStatus, SuiteResult, run_suite
from mcp_rig.spec import SpecError, load_suite


class BatchFailureCategory(StrEnum):
    CONFIGURATION = "configuration"
    EXECUTION = "execution"


@dataclass(frozen=True)
class BatchFailure:
    category: BatchFailureCategory
    exception_type: str
    message: str


@dataclass(frozen=True)
class SuiteRun:
    path: Path
    result: SuiteResult | None = None
    error: BatchFailure | None = None


@dataclass(frozen=True)
class BatchResult:
    suites: list[SuiteRun]
    discovery_errors: list[DiscoveryError]

    @property
    def suite_passed(self) -> int:
        return sum(item.result is not None and item.result.ok for item in self.suites)

    @property
    def suite_failed(self) -> int:
        return sum(
            item.result is not None
            and item.result.failed > 0
            and item.result.errors == 0
            for item in self.suites
        )

    @property
    def suite_errors(self) -> int:
        return len(self.discovery_errors) + sum(
            item.error is not None
            or item.result is not None
            and item.result.errors > 0
            for item in self.suites
        )

    @property
    def case_passed(self) -> int:
        return sum(item.result.passed for item in self.suites if item.result is not None)

    @property
    def case_failed(self) -> int:
        return sum(item.result.failed for item in self.suites if item.result is not None)

    @property
    def case_errors(self) -> int:
        return sum(
            sum(case.status is CaseStatus.ERROR for case in item.result.results)
            for item in self.suites
            if item.result is not None
        )

    @property
    def case_skipped(self) -> int:
        return sum(item.result.skipped for item in self.suites if item.result is not None)

    @property
    def has_failures(self) -> bool:
        return self.case_failed > 0

    @property
    def has_errors(self) -> bool:
        return self.suite_errors > 0


async def run_batch(
    discovery: DiscoveryResult,
    show_server_logs: bool = False,
) -> BatchResult:
    suites: list[SuiteRun] = []
    for path in discovery.paths:
        try:
            suite = load_suite(path)
        except SpecError as exc:
            suites.append(
                SuiteRun(
                    path,
                    error=_failure(BatchFailureCategory.CONFIGURATION, exc),
                )
            )
            continue

        try:
            result = await run_suite(suite, show_server_logs=show_server_logs)
        except Exception as exc:
            suites.append(
                SuiteRun(
                    path,
                    error=_failure(BatchFailureCategory.EXECUTION, exc),
                )
            )
            continue
        suites.append(SuiteRun(path, result=result))

    return BatchResult(suites=suites, discovery_errors=discovery.errors)


def _failure(category: BatchFailureCategory, exc: Exception) -> BatchFailure:
    return BatchFailure(
        category=category,
        exception_type=type(exc).__name__,
        message=str(exc) or type(exc).__name__,
    )
