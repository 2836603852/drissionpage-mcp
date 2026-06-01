# -*- coding: utf-8 -*-
"""
DrissionPage MCP server entry point.
"""

import argparse
import sys
from contextlib import asynccontextmanager
from typing import Optional

# Try importing FastMCP from supported packages.
try:
    from fastmcp import FastMCP
except ImportError:
    # Fallback import path.
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Error: install fastmcp (or mcp package) first.", file=sys.stderr)
        print("pip install fastmcp", file=sys.stderr)
        sys.exit(1)

from .browser_manager import browser_manager
from .config import Config
from .tools import (
    register_actions_tools,
    register_debugger_tools,
    register_element_operations_tools,
    register_javascript_tools,
    register_network_tools,
    register_page_management_tools,
    register_screenshot_tools,
    register_websocket_tools,
)

# Global runtime configuration.
config: Optional[Config] = None

# Default debug port when --debug-port is not supplied on the command line.
# 9223 keeps us off the standard Chrome remote-debugging port (9222) so this
# MCP does not collide with a user's manually launched Chromium on :9222.
DEFAULT_DEBUG_PORT = 9223

# CLI-provided debug port (None until main() parses argv).
_cli_debug_port: Optional[int] = None


def _log(message: str) -> None:
    """Best-effort log to stderr (safe for stdio transport shutdown)."""
    try:
        print(message, file=sys.stderr, flush=True)
    except Exception:
        # Ignore stream-closed errors during transport teardown.
        pass


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Server lifecycle management."""
    global config

    # Startup initialization.
    config = Config()
    if _cli_debug_port is not None:
        config.browser.debug_port = _cli_debug_port
    browser_manager.set_config(config)
    runtime_debug_port = browser_manager.get_debug_port()

    _log(f"[{config.server.name}] Server started v{config.server.version}")
    _log(f"[{config.server.name}] DrissionPage-based browser automation MCP server")
    _log(f"[{config.server.name}] Runtime debug port fixed to {runtime_debug_port}")

    yield {
        "config": config,
        "browser_manager": browser_manager,
        "runtime_debug_port": runtime_debug_port,
    }

    # Shutdown cleanup.
    _log(f"[{config.server.name}] Server shutting down, cleaning resources...")
    browser_manager.close_all()


# Create MCP server.
mcp = FastMCP(
    "DrissionPage MCP",
    lifespan=app_lifespan
)


# Register all tools.
def _register_all_tools():
    """Register all tools."""
    register_page_management_tools(mcp)
    register_element_operations_tools(mcp)
    register_javascript_tools(mcp)
    register_network_tools(mcp)
    register_actions_tools(mcp)
    register_screenshot_tools(mcp)
    register_websocket_tools(mcp)
    register_debugger_tools(mcp)
    _log("[DrissionPage MCP] 44 tools loaded (31 core + 3 ws-frame + 10 debugger)")


# Register resources.
@mcp.resource("browser://status")
async def get_browser_status():
    """Get browser status resource."""
    sessions = browser_manager.list_sessions()

    return {
        "status": "ready" if sessions else "no_browser",
        "default_browser": browser_manager.default_session_id,
        "runtime_debug_port": browser_manager.get_debug_port(),
        "browsers": sessions,
    }


def _parse_cli_args(argv: Optional[list] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="drissionpage-mcp",
        description="DrissionPage MCP server (browser automation, stdio or HTTP).",
    )

    # Chromium debug-port group (mutually exclusive)
    port_group = parser.add_mutually_exclusive_group()
    port_group.add_argument(
        "--debug-port",
        type=int,
        default=None,
        metavar="PORT",
        help=(
            f"Fix the runtime Chromium debug port (1-65535). "
            f"Defaults to {DEFAULT_DEBUG_PORT} when neither --debug-port nor "
            "--auto-port is supplied."
        ),
    )
    port_group.add_argument(
        "--auto-port",
        action="store_true",
        help=(
            "Pick a free localhost port at startup instead of using the "
            f"default {DEFAULT_DEBUG_PORT}. Use this when running multiple "
            "MCP instances concurrently to avoid port collisions."
        ),
    )

    # MCP transport group
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport. Default 'stdio' for local clients; 'http' exposes the server over HTTP for remote clients.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP host bind address (only used when --transport != stdio). Default 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help="HTTP port (only used when --transport != stdio). Default 8000.",
    )

    return parser.parse_args(argv)


def _pick_free_port() -> int:
    """Pick a currently-free localhost TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main():
    """Main entry point."""
    global _cli_debug_port
    args = _parse_cli_args()

    if args.auto_port:
        debug_port = _pick_free_port()
    else:
        debug_port = args.debug_port if args.debug_port is not None else DEFAULT_DEBUG_PORT

    if not (0 < debug_port < 65536):
        print(
            f"Error: --debug-port must be in range 1-65535, got {debug_port}",
            file=sys.stderr,
        )
        sys.exit(2)
    _cli_debug_port = debug_port

    if args.transport != "stdio" and not (0 < args.port < 65536):
        print(
            f"Error: --port must be in range 1-65535, got {args.port}",
            file=sys.stderr,
        )
        sys.exit(2)

    _register_all_tools()

    if args.transport == "stdio":
        mcp.run(show_banner=False)
    else:
        _log(f"[DrissionPage MCP] Serving over {args.transport} on {args.host}:{args.port}")
        mcp.run(transport=args.transport, host=args.host, port=args.port, show_banner=False)


if __name__ == "__main__":
    main()
