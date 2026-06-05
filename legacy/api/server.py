"""aiohttp app factory — wires routes, middleware, and configuration."""

from pathlib import Path

from aiohttp import web

from api.middleware import cors_middleware, error_middleware
from api.routes_data import (
    get_status,
    get_data,
    get_history,
    get_history_item,
)
from api.routes_settings import get_settings, post_settings
from api.routes_run import post_run, post_cancel
from api.routes_stream import get_stream
from orchestrator import Orchestrator


def create_app(
    orchestrator: Orchestrator,
    settings_path: Path = Path("settings.json"),
    port: int = 8421,
) -> web.Application:
    """
    Create and return the configured aiohttp Application.
    Registers all routes and middleware.
    """
    app = web.Application(middlewares=[error_middleware, cors_middleware])

    # Store references in app for route handlers to access
    app["orchestrator"] = orchestrator
    app["settings_path"] = settings_path
    app["port"] = port

    # Register API routes
    # Data endpoints
    app.router.add_get("/api/status", get_status)
    app.router.add_get("/api/data", get_data)
    app.router.add_get("/api/history", get_history)
    app.router.add_get("/api/history/{id}", get_history_item)

    # Settings endpoints
    app.router.add_get("/api/settings", get_settings)
    app.router.add_post("/api/settings", post_settings)

    # Job control endpoints
    app.router.add_post("/api/run", post_run)
    app.router.add_post("/api/cancel", post_cancel)

    # SSE stream endpoint
    app.router.add_get("/api/stream", get_stream)

    # Frontend placeholder routes
    app.router.add_get("/", _frontend_placeholder)
    app.router.add_get("/{tail:.*}", _frontend_placeholder)

    return app


async def _frontend_placeholder(request: web.Request) -> web.Response:
    """Placeholder frontend response."""
    return web.Response(
        text="Frontend coming in Phase 4",
        content_type="text/plain",
    )

