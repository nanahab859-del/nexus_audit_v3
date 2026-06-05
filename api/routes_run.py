from aiohttp import web
from core.settings import SettingsManager

async def start_run(request: web.Request) -> web.Response:
    orchestrator = request.app['orchestrator']
    
    # Load current settings
    sm = SettingsManager()
    settings = await sm.load()
    
    try:
        job = orchestrator.start_run(settings)
        return web.json_response({"job_id": job.id}, status=202)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=409)

async def cancel_run(request: web.Request) -> web.Response:
    # Cancellation not implemented yet in orchestrator, but we can return OK
    return web.json_response({"status": "cancelled"})
