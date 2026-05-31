"""HTTP middleware for CORS and JSON error handling."""

import sys
import traceback
from typing import Callable

from aiohttp import web
from core.settings import SettingsValidationError
from orchestrator import ConflictError


async def cors_middleware(
    app: web.Application, handler: Callable
) -> Callable:
    """
    CORS middleware — allows localhost only for API routes.
    Skips CORS validation for static files.
    """

    async def middleware_handler(request: web.Request) -> web.Response:
        origin = request.headers.get("Origin", "")
        path = request.path

        # Only validate CORS for API routes
        if path.startswith("/api/"):
            # Only allow localhost origins
            if origin and not (
                origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")
            ):
                return web.json_response(
                    {"error": "Forbidden", "message": "CORS policy violation"},
                    status=403,
                )

        # Handle OPTIONS preflight
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)

        # Add CORS headers for API requests
        if origin and path.startswith("/api/"):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization"
            )

        return response

    return middleware_handler


async def error_middleware(
    app: web.Application, handler: Callable
) -> Callable:
    """
    JSON error middleware — catches exceptions and returns JSON.
    """

    async def middleware_handler(request: web.Request) -> web.Response:
        try:
            return await handler(request)
        except ConflictError as e:
            return web.json_response(
                {
                    "error": "Conflict",
                    "message": str(e),
                },
                status=409,
            )
        except SettingsValidationError as e:
            return web.json_response(
                {
                    "error": "ValidationError",
                    "message": str(e),
                },
                status=400,
            )
        except FileNotFoundError as e:
            return web.json_response(
                {
                    "error": "NotFound",
                    "message": str(e),
                },
                status=404,
            )
        except web.HTTPException:
            raise
        except Exception as e:
            print(f"Unhandled exception: {e}", file=sys.stderr)
            print(f"Exception type: {type(e).__name__}")
            traceback.print_exc()
            return web.json_response(
                {
                    "error": "InternalServerError",
                    "message": "An unexpected error occurred",
                },
                status=500,
            )

    return middleware_handler
