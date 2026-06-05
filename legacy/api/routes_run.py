"""Job control endpoints — start and cancel audit scans."""

from pathlib import Path

from aiohttp import web

from core.settings import load as load_settings
from orchestrator import Orchestrator


async def post_run(request: web.Request) -> web.Response:
    """POST /api/run — start a new audit job."""
    orchestrator: Orchestrator = request.app["orchestrator"]
    settings_path: Path = request.app["settings_path"]

    # Load current settings
    settings = load_settings(settings_path)

    # Validate project_path exists
    if not settings.project_path.exists():
        raise FileNotFoundError(
            f"Project path does not exist: {settings.project_path}"
        )

    # Start the job
    job = await orchestrator.start_job(settings.project_path, settings)

    return web.json_response({"job_id": job.id}, status=202)


async def post_cancel(request: web.Request) -> web.Response:
    """POST /api/cancel — cancel the running job."""
    orchestrator: Orchestrator = request.app["orchestrator"]

    await orchestrator.cancel_job()

    return web.json_response({"ok": True})
