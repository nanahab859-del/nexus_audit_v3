"""Settings endpoints — read and write configuration."""

from pathlib import Path
from typing import Any

from aiohttp import web

from core.security import encrypt
from core.settings import load as load_settings
from core.settings import save as save_settings
from core.models import Settings


async def get_settings(request: web.Request) -> web.Response:
    """GET /api/settings — return current settings with redacted api_key."""
    settings_path: Path = request.app["settings_path"]
    settings = load_settings(settings_path)

    # Convert to dict and redact api_key
    result: dict[str, Any] = {
        "project_path": str(settings.project_path),
        "api_key": "***" if settings.api_key else None,
        "ai_enabled": settings.ai_enabled,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "force_rescan": settings.force_rescan,
        "scanners": settings.scanners,
        "scanner_configs": settings.scanner_configs,
        "ui": settings.ui,
    }

    return web.json_response(result)


async def post_settings(request: web.Request) -> web.Response:
    """POST /api/settings — update settings."""
    settings_path: Path = request.app["settings_path"]
    body = await request.json()

    # Load current settings
    current_settings = load_settings(settings_path)

    # Handle api_key: "***" means preserve existing
    api_key = body.get("api_key")
    if api_key == "***":
        # Keep existing
        api_key = current_settings.api_key
    elif api_key:
        # Encrypt new key
        api_key = encrypt(api_key)

    # Create new settings object
    new_settings = Settings(
        project_path=Path(body.get("project_path", current_settings.project_path)),
        api_key=api_key,
        ai_enabled=body.get("ai_enabled", current_settings.ai_enabled),
        ai_provider=body.get("ai_provider", current_settings.ai_provider),
        ai_model=body.get("ai_model", current_settings.ai_model),
        force_rescan=body.get("force_rescan", current_settings.force_rescan),
        scanners=body.get("scanners", current_settings.scanners),
        scanner_configs=body.get("scanner_configs", current_settings.scanner_configs),
        ui=body.get("ui", current_settings.ui),
    )

    # Save settings
    await save_settings(new_settings, settings_path)

    # Update app reference
    request.app["settings"] = new_settings

    return web.json_response({"ok": True})
