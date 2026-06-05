from aiohttp import web
from pathlib import Path
from api import routes_data, routes_run, routes_settings, routes_stream

def create_app(argv=None) -> web.Application:
    app = web.Application()
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

    # API routes registered FIRST (highest priority)
    app.router.add_get('/api/status', routes_data.get_status)
    app.router.add_get('/api/data', routes_data.get_data)
    app.router.add_post('/api/run', routes_run.start_run)
    app.router.add_post('/api/cancel', routes_run.cancel_run)
    app.router.add_get('/api/settings', routes_settings.get_settings)
    app.router.add_post('/api/settings', routes_settings.update_settings)
    app.router.add_get('/api/stream', routes_stream.stream)

    # Static asset directories (CSS, JS, assets)
    app.router.add_static('/static/css',    FRONTEND_DIR / 'css')
    app.router.add_static('/static/js',     FRONTEND_DIR / 'js')
    app.router.add_static('/static/assets', FRONTEND_DIR / 'assets')

    # SPA catch-all — MUST be last
    async def spa_fallback(request: web.Request) -> web.FileResponse:
        return web.FileResponse(FRONTEND_DIR / 'index.html')

    app.router.add_get('/', spa_fallback)
    app.router.add_get('/{tail:.*}', spa_fallback)

    return app
