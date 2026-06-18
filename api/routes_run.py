from __future__ import annotations
from aiohttp import web
from core.primitives.settings import SettingsManager


async def start_run(request: web.Request) -> web.Response:
    orchestrator = request.app['orchestrator']
    sm: SettingsManager = request.app['sm']

    data = {}
    if request.can_read_body:
        try:
            data = await request.json()
        except Exception:
            pass

    fast      = data.get("fast", False)
    workspace = await sm.load_workspace()

    if not workspace.active_project_id:
        return web.json_response(
            {"error": "No active project. Register a project first."}, status=409
        )

    try:
        await sm.load_project(workspace.active_project_id)   # ensure cached
        job = await orchestrator.start_job(
            workspace.active_project_id,
            fast_mode=fast,
        )
        return web.json_response({"job_id": job.id}, status=202)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=409)


async def cancel_run(request: web.Request) -> web.Response:
    orchestrator = request.app['orchestrator']
    try:
        await orchestrator.cancel_job()
        return web.json_response({"status": "cancelled"}, status=202)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=409)
