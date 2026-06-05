from aiohttp import web
from core.settings import load as load_settings
from core.fix_queue import FixQueue

async def get_fixqueue(request: web.Request) -> web.Response:
    """GET /api/fixqueue"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    queue = FixQueue(settings.project_path / ".nexus_fix_queue.json")
    return web.json_response(queue.get_all())

async def post_fixqueue(request: web.Request) -> web.Response:
    """POST /api/fixqueue/{finding_id}"""
    finding_id = request.match_info["id"]
    
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON payload"}, status=400)
        
    status = data.get("status")
    if status not in ("open", "in_progress", "done", "snoozed"):
        return web.json_response({"error": f"Invalid status: {status}"}, status=400)
        
    note = data.get("note", "")
    
    app = request.app
    settings = load_settings(app["settings_path"])
    
    queue = FixQueue(settings.project_path / ".nexus_fix_queue.json")
    queue.update_status(finding_id, status, note)
    
    return web.json_response({"success": True})
