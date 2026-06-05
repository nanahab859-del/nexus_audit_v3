"""HTTP middleware for CORS and JSON error handling."""

import sys
from typing import Callable

from aiohttp import web
from core.settings import SettingsValidationError
from orchestrator import ConflictError


async def cors_middleware(
    app: web.Application, handler: Callable
) -> Callable:
    """
    CORS middleware — allows localhost only.
    Rejects requests from other origins with 403.
    """

    async def middleware_handler(request: web.Request) -> web.Response:
        origin = request.headers.get("Origin", "")

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

        # Add CORS headers
        if origin:
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
            return web.json_response(
                {
                    "error": "InternalServerError",
                    "message": "An unexpected error occurred",
                },
                status=500,
            )

    return middleware_handler
