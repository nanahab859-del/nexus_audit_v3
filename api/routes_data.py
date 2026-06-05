from aiohttp import web
from pathlib import Path
from core.atomic import read_json

async def get_status(request: web.Request) -> web.Response:
    orchestrator = request.app['orchestrator']
    job = orchestrator.current_job
    if job:
        return web.json_response({"state": job.state, "job_id": job.id})
    return web.json_response({"state": "idle", "job_id": None})

async def get_data(request: web.Request) -> web.Response:
    data = await read_json(Path("audit_data_complete.json"))
    if data is None:
        return web.json_response(_EMPTY_DATA_RESPONSE)
    return web.json_response(data)

_EMPTY_DATA_RESPONSE = {
    "metadata": {"job_id": None, "project_path": "", "started_at": None,
                 "finished_at": None, "total_findings": 0, "total_violations": 0,
                 "git_context": {}},
    "findings": [],
    "apps": {},
    "fleet_average": 0.0,
    "coupling_matrix": {"apps": [], "matrix": [], "details": {}},
    "dna": {},
    "config_health": [],
    "dependency_scan": [],
    "recommendations": [],
    "change_summary": {"first_run": True, "new_violations": 0,
                      "resolved_violations": 0, "score_deltas": {}},
    "rules_summary": []
}
