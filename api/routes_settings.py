from aiohttp import web

async def get_settings(request: web.Request) -> web.Response:
    return web.json_response({})

async def update_settings(request: web.Request) -> web.Response:
    return web.json_response({"status": "updated"})
