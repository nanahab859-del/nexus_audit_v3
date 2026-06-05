from aiohttp import web
from core.settings import load as load_settings
from core.timeline import load_score_history

async def get_trends(request: web.Request) -> web.Response:
    """GET /api/trends"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    history_dir = settings.project_path / "audit_history"
    trends = load_score_history(history_dir)
    
    return web.json_response(trends)
