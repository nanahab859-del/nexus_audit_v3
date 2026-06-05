"""
Nexus Audit V3 — server entry point.
Usage: python server.py [--port 8421] [--settings path/to/settings.json]
"""

import argparse
from pathlib import Path

from aiohttp import web

from api.server import create_app
from orchestrator import Orchestrator


def main() -> None:
    """Start the Nexus Audit V3 server."""
    parser = argparse.ArgumentParser(description="Nexus Audit V3 Server")
    parser.add_argument("--port", type=int, default=8421, help="Port to listen on")
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("settings.json"),
        help="Path to settings file",
    )
    args = parser.parse_args()

    orc = Orchestrator()
    app = create_app(orc, settings_path=args.settings, port=args.port)

    web.run_app(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
