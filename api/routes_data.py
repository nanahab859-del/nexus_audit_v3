from aiohttp import web

async def get_status(request: web.Request) -> web.Response:
    return web.json_response({"state": "idle", "job_id": None})

async def get_data(request: web.Request) -> web.Response:
    # Placeholder for reading audit_data_complete.json
    return web.json_response({})
