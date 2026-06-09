# api/routes_ai.py
"""
AI-assisted diagnostic endpoints.

POST /api/ai/diagnose-scanner-error
  Accepts an error context (scanner name, error message, surrounding logs)
  and returns a plain-text diagnostic summary.

NOTE: The actual AI call is a stub until the AI provider settings are fully
wired up. When ready, replace the stub body with a real provider call using
the api_key and ai_provider from Settings.
"""

from aiohttp import web
from core.settings import SettingsManager

STUB_ADVICE: dict[str, str] = {
    "vulture":  "Vulture did not find a valid Python interpreter. Make sure vulture is installed in the project virtual environment: `pip install vulture`.",
    "bandit":   "Bandit could not parse the target. Check that the project_path points to valid Python source files and that bandit is installed: `pip install bandit`.",
    "safety":   "Safety timed out during dependency resolution. This can happen with circular dependencies or a slow PyPI mirror. Try running with `force_rescan: true` to clear the cache, or increase the scanner timeout in the Scanners tab.",
}

GENERIC_ADVICE = (
    "The scanner encountered an unexpected error. "
    "Check that the required tool is installed in the project virtual environment and that "
    "the project_path points to the correct directory. "
    "Review the full error message above for additional details."
)


async def diagnose_scanner_error(request: web.Request) -> web.Response:
    """
    POST /api/ai/diagnose-scanner-error

    Request JSON:
      {
        "scanner_name":  "safety",
        "error_message": "TimeoutError: Scanner timed out after 120s",
        "context_logs":  ["...", "..."]   // optional
      }

    Response JSON:
      { "analysis": "..." }
    Or, when AI is disabled:
      { "error": "AI is not enabled" }  (HTTP 503)
    """
    sm = SettingsManager()
    settings = await sm.load()

    if not settings.ai_enabled:
        return web.json_response(
            {"error": "AI diagnostics are not enabled. Enable AI in the Settings tab and provide an API key."},
            status=503,
        )

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    scanner_name  = str(body.get("scanner_name", "")).strip().lower()
    error_message = str(body.get("error_message", "")).strip()

    if not scanner_name or not error_message:
        return web.json_response({"error": "scanner_name and error_message are required"}, status=400)

    # ── Stub: return canned advice until the AI provider is wired ──────────
    # TODO: replace this block with a real AI provider call once
    #       settings.api_key / settings.ai_provider are fully implemented.
    analysis = STUB_ADVICE.get(scanner_name, GENERIC_ADVICE)

    return web.json_response({"analysis": analysis})
