from aiohttp import web
from pathlib import Path
from api import routes_data, routes_run, routes_settings, routes_stream, routes_config, routes_project, routes_ai
from core.primitives.settings import SettingsManager
from core.infra.registry import PluginRegistry
from orchestrator import Orchestrator

def create_app(argv=None) -> web.Application:
    app = web.Application()

    # Fix 1: SettingsManager constructed first, passed to Orchestrator.
    # Bus is derived from orchestrator.bus so routes_stream subscribes to
    # the same bus the orchestrator publishes on.
    sm           = SettingsManager()
    orchestrator = Orchestrator(sm)
    bus          = orchestrator.bus

    # Shared plugin registry — stored on app so reload_registry can update it
    registry = PluginRegistry(Path("plugins"))
    registry.load()

    app['sm']           = sm
    app['bus']          = bus
    app['orchestrator'] = orchestrator
    app['registry']     = registry

    FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

    # API routes registered FIRST (highest priority)
    app.router.add_get('/api/status',   routes_data.get_status)
    app.router.add_get('/api/data',     routes_data.get_data)
    app.router.add_get('/api/capabilities', routes_data.get_capabilities)
    app.router.add_post('/api/run',     routes_run.start_run)
    app.router.add_post('/api/cancel',  routes_run.cancel_run)
    app.router.add_get('/api/settings', routes_settings.get_settings)
    app.router.add_post('/api/settings', routes_settings.update_settings)
    app.router.add_get('/api/stream',   routes_stream.stream)

    # Project-specific routes
    app.router.add_post('/api/project/ping',            routes_project.ping_project)
    app.router.add_post('/api/project/validate-remote', routes_project.validate_remote)

    # Config + scanner management routes
    app.router.add_get('/api/config',              routes_config.get_config)
    app.router.add_post('/api/config',             routes_config.save_config)
    app.router.add_get('/api/config/yaml',         routes_config.get_yaml)
    app.router.add_post('/api/config/validate',    routes_config.validate_config_endpoint)
    app.router.add_get('/api/config/sync_identity', routes_config.sync_identity)
    app.router.add_get('/api/scanners',            routes_config.get_scanners)
    app.router.add_post('/api/registry/reload',    routes_config.reload_registry)
    app.router.add_get('/api/scanners/status',     routes_config.get_scanners_status)
    app.router.add_post('/api/scanners/install',   routes_config.install_scanner)
    # AI diagnostic routes
    app.router.add_post('/api/ai/diagnose-scanner-error', routes_ai.diagnose_scanner_error)
    app.router.add_post('/api/ai/test',           routes_ai.test_connection)
    app.router.add_get('/api/ai/usage',           routes_ai.get_usage)
    app.router.add_get('/api/ai/ollama/models',   routes_ai.get_ollama_models)

    app.router.add_post('/api/scanners/custom',    routes_config.register_custom_scanner)
    app.router.add_delete('/api/scanners/custom/{name}', routes_config.delete_custom_scanner)

    # VEX suppression routes
    app.router.add_get('/api/vex',            routes_config.get_vex)
    app.router.add_delete('/api/vex',         routes_config.delete_vex)
    app.router.add_post('/api/vex/upload',    routes_config.upload_vex)

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
