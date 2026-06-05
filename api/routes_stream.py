from aiohttp import web

async def stream(request: web.Request) -> web.Response:
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)
    await response.write(b'data: connected\n\n')
    return response
