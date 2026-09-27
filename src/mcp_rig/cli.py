"""Command-line entry point for MCP Rig."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anyio

from mcp_rig.checks import CheckResult, run_protocol_checks
from mcp_rig.client import ServerSpec, connect
from mcp_rig.junit import write_junit
from mcp_rig.lint import LintWarning, lint_tools
from mcp_rig.report import render_check, render_suite
from mcp_rig.runner import run_suite
from mcp_rig.spec import SpecError, load_suite

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-rig",
        description="Deterministic tests for MCP servers.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run a YAML tool suite")
    run_parser.add_argument("suite", help="path to a YAML suite")
    run_parser.add_argument(
        "--server-logs",
        action="store_true",
        help="show the MCP server's stderr",
    )
    run_parser.add_argument(
        "--junit",
        metavar="PATH",
        help="also write a JUnit XML report",
    )
    check_parser = commands.add_parser(
        "check",
        help="run protocol checks and tool lint without a suite",
    )
    check_parser.add_argument(
        "server",
        help='server command, for example "python server.py"',
    )
    check_parser.add_argument(
        "--probe-invalid-args",
        action="store_true",
        help="call tools with missing required args; only use on development/test servers",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when tool lint produces warnings",
    )
    check_parser.add_argument(
        "--server-logs",
        action="store_true",
        help="show the MCP server's stderr",
    )

    args = parser.parse_args(argv)
    color = sys.stdout.isatty()
    if args.command == "run":
        return _cmd_run(args, color=color)
    return _cmd_check(args, color=color)


def _cmd_run(args: argparse.Namespace, color: bool) -> int:
    if args.junit and _same_path(args.suite, args.junit):
        print("error: JUnit report path must differ from suite path", file=sys.stderr)
        return EXIT_USAGE
    try:
        suite = load_suite(args.suite)
        result = anyio.run(run_suite, suite, args.server_logs)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - CLI converts infrastructure errors to exit 2
        print(f"error: {args.suite}: could not run server: {_describe(exc)}", file=sys.stderr)
        return EXIT_USAGE

    print(render_suite(args.suite, result, color=color))
    if args.junit:
        try:
            write_junit(args.junit, args.suite, result)
        except OSError as exc:
            print(f"error: {args.junit}: could not write JUnit report: {_describe(exc)}", file=sys.stderr)
            return EXIT_USAGE
    if result.errors:
        return EXIT_USAGE
    if result.failed:
        return EXIT_FAILED
    return EXIT_OK


def _cmd_check(args: argparse.Namespace, color: bool) -> int:
    try:
        spec = ServerSpec.from_command_line(args.server)
        checks, warnings = anyio.run(
            _check,
            spec,
            args.probe_invalid_args,
            args.server_logs,
        )
    except Exception as exc:  # noqa: BLE001 - CLI converts infrastructure errors to exit 2
        print(f"error: could not run server: {_describe(exc)}", file=sys.stderr)
        return EXIT_USAGE

    print(render_check(checks, warnings, color=color))
    failed = not all(check.passed for check in checks) or (
        args.strict and bool(warnings)
    )
    return EXIT_FAILED if failed else EXIT_OK


async def _check(
    spec: ServerSpec,
    probe_invalid_args: bool,
    show_server_logs: bool,
) -> tuple[list[CheckResult], list[LintWarning]]:
    async with connect(spec, show_server_logs=show_server_logs) as probe:
        tools = await probe.list_tools()
        checks = await run_protocol_checks(
            probe,
            probe_invalid_args=probe_invalid_args,
        )
    return checks, lint_tools(tools)


def _describe(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


def _same_path(first: str, second: str) -> bool:
    try:
        return Path(first).samefile(second)
    except OSError:
        return Path(first).resolve() == Path(second).resolve()
