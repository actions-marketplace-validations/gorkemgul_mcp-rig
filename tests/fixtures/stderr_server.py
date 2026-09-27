"""Fixture server that emits a startup diagnostic on stderr."""

import sys

from fixture_server import server

if __name__ == "__main__":
    print("mcp-rig-check-server-log", file=sys.stderr, flush=True)
    server.run()
