"""Command-line entry point for MCP Rig."""

from __future__ import annotations

import argparse
import sys

import anyio

from mcp_rig.junit import write_junit
from mcp_rig.report import render_suite
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

    args = parser.parse_args(argv)
    return _run(args, color=sys.stdout.isatty())


def _run(args: argparse.Namespace, color: bool) -> int:
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


def _describe(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"
