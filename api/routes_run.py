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
    orchestrator = request.app['orchestrator']
    try:
        job = await orchestrator.cancel_run()
        return web.json_response({"status": "cancelled", "job_id": job.id}, status=202)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=409)
