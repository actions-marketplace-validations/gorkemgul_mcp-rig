"""Run suite cases sequentially against one MCP server process."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

from mcp.shared.exceptions import MCPError
from mcp_types import REQUEST_TIMEOUT

from mcp_rig.assertions import check
from mcp_rig.client import CallOutcome, Probe, connect
from mcp_rig.spec import Case, Suite


class CaseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class ErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    SETUP = "setup"
    TRANSPORT = "transport"
    TEARDOWN = "teardown"


@dataclass(frozen=True)
class InfrastructureError:
    category: ErrorCategory
    exception_type: str
    message: str


@dataclass(frozen=True)
class CaseResult:
    name: str
    status: CaseStatus
    elapsed_ms: float = 0.0
    failures: list[str] = field(default_factory=list)
    outcome: CallOutcome | None = None
    error: InfrastructureError | None = None
    skip_reason: str | None = None


@dataclass(frozen=True)
class SuiteResult:
    results: list[CaseResult]
    suite_error: InfrastructureError | None = None

    @property
    def passed(self) -> int:
        return sum(item.status is CaseStatus.PASSED for item in self.results)

    @property
    def failed(self) -> int:
        return sum(item.status is CaseStatus.FAILED for item in self.results)

    @property
    def errors(self) -> int:
        return sum(item.status is CaseStatus.ERROR for item in self.results) + (self.suite_error is not None)

    @property
    def skipped(self) -> int:
        return sum(item.status is CaseStatus.SKIPPED for item in self.results)

    @property
    def ok(self) -> bool:
        return bool(self.results) and self.passed == len(self.results) and self.suite_error is None


async def run_suite(suite: Suite, show_server_logs: bool = False) -> SuiteResult:
    results: list[CaseResult] = []
    async with connect(suite.server, show_server_logs=show_server_logs) as probe:
        for index, case in enumerate(suite.cases):
            result = await _run_case(probe, case)
            results.append(result)
            if result.status is CaseStatus.ERROR:
                reason = f"not run after infrastructure error in '{case.name}'"
                results.extend(
                    CaseResult(name=remaining.name, status=CaseStatus.SKIPPED, skip_reason=reason)
                    for remaining in suite.cases[index + 1 :]
                )
                break
    return SuiteResult(results)


async def _run_case(probe: Probe, case: Case) -> CaseResult:
    started = time.perf_counter()
    try:
        outcome = await probe.call(case.call, case.args, timeout_s=case.timeout_s)
    except Exception as exc:
        return CaseResult(
            name=case.name,
            status=CaseStatus.ERROR,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            error=_normalize_error(exc, ErrorCategory.TRANSPORT),
        )
    failures = check(case.expect, outcome)
    return CaseResult(
        name=case.name,
        status=CaseStatus.FAILED if failures else CaseStatus.PASSED,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        failures=failures,
        outcome=outcome,
    )


def _normalize_error(exc: BaseException, fallback: ErrorCategory) -> InfrastructureError:
    leaves = _exception_leaves(exc)
    selected = next((leaf for leaf in leaves if _is_timeout(leaf)), leaves[0])
    category = ErrorCategory.TIMEOUT if fallback is ErrorCategory.TRANSPORT and _is_timeout(selected) else fallback
    message = str(selected) or ("operation timed out" if _is_timeout(selected) else type(selected).__name__)
    return InfrastructureError(category=category, exception_type=type(selected).__name__, message=message)


def _exception_leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for nested in exc.exceptions for leaf in _exception_leaves(nested)]
    return [exc]


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or isinstance(exc, MCPError) and exc.code == REQUEST_TIMEOUT
