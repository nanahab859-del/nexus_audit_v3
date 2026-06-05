from aiohttp import web

async def start_run(request: web.Request) -> web.Response:
    return web.json_response({"status": "started"})

async def cancel_run(request: web.Request) -> web.Response:
    return web.json_response({"status": "cancelled"})
