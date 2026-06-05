"""Data endpoints — read-only access to audit results."""

from pathlib import Path

from aiohttp import web

from core.atomic import read_json
from orchestrator import Orchestrator


async def get_status(request: web.Request) -> web.Response:
    """GET /api/status — return current job status."""
    orchestrator: Orchestrator = request.app["orchestrator"]
    return web.json_response(orchestrator.status())


async def get_data(request: web.Request) -> web.Response:
    """GET /api/data — return latest audit results."""
    data = await read_json(Path("audit_data_complete.json"))

    if data is None:
        return web.json_response({"findings": [], "job": None})

    return web.json_response(data)


async def get_history(request: web.Request) -> web.Response:
    """GET /api/history — list all past audits."""
    history_dir = Path("audit_history")

    if not history_dir.exists():
        return web.json_response([])

    # Get all JSON files, sorted newest first
    files = sorted(history_dir.glob("*.json"), reverse=True)
    history_list = []

    for file_path in files:
        data = await read_json(file_path)
        if data:
            finding_count = 0
            if "scan_results" in data:
                finding_count = sum(len(sr.get("findings", [])) for sr in data["scan_results"])

            history_list.append(
                {
                    "id": file_path.stem,
                    "timestamp": data.get("started_at", ""),
                    "finding_count": finding_count,
                }
            )

    return web.json_response(history_list)


async def get_history_item(request: web.Request) -> web.Response:
    """GET /api/history/{id} — return a specific past audit."""
    item_id = request.match_info["id"]
    file_path = Path("audit_history") / f"{item_id}.json"

    data = await read_json(file_path)
    if data is None:
        raise FileNotFoundError(f"History item not found: {item_id}")

    return web.json_response(data)
