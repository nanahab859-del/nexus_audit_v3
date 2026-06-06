from aiohttp import web
from dataclasses import asdict
from core.settings import SettingsManager

# Whitelist of allowed settings keys to prevent injection of invalid fields
ALLOWED_SETTINGS_KEYS = {
    "project_path", "api_key", "ai_enabled", "ai_provider",
    "ai_model", "force_rescan", "scanners", "scanner_configs", "ui"
}

async def get_settings(request: web.Request) -> web.Response:
    sm = SettingsManager()
    settings = await sm.load()
    return web.json_response(asdict(settings))

async def update_settings(request: web.Request) -> web.Response:
    sm = SettingsManager()
    settings = await sm.load()
    data = await request.json()

    # Only allow whitelisted keys to be updated
    for key, value in data.items():
        if key in ALLOWED_SETTINGS_KEYS and hasattr(settings, key):
            setattr(settings, key, value)

    await sm.save()
    return web.json_response({"status": "updated"})
