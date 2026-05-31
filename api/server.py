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

    # Register API routes (these take precedence over static files)
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

    # Serve frontend static files
    # This must come after API routes so API takes precedence
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        # Serve HTML and assets from root
        app.router.add_get("/", _serve_index)
        app.router.add_static("/static", path=frontend_dir, name="frontend")

    # Fallback SPA route - serve index.html for any unmatched route
    # This supports SPA routing and fixes 403 errors on directory access
    app.router.add_get("/{tail:.*}", _serve_spa_fallback)

    return app


async def _serve_index(request: web.Request) -> web.Response:
    """Serve index.html at root."""
    frontend_dir = Path(__file__).parent.parent / "frontend"
    index_path = frontend_dir / "index.html"
    
    if index_path.exists():
        return web.FileResponse(index_path)
    
    return web.Response(
        text="Frontend index.html not found",
        content_type="text/plain",
        status=404,
    )


async def _serve_spa_fallback(request: web.Request) -> web.Response:
    """Fallback handler for SPA routing - serves index.html for unmatched routes."""
    frontend_dir = Path(__file__).parent.parent / "frontend"
    index_path = frontend_dir / "index.html"
    
    if index_path.exists():
        return web.FileResponse(index_path)
    
    return web.Response(
        text="Frontend index.html not found",
        content_type="text/plain",
        status=404,
    )

