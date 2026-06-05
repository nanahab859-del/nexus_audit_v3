from aiohttp import web
from core.settings import load as load_settings

async def get_report_markdown(request: web.Request) -> web.StreamResponse:
    """GET /api/report/markdown"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    report_path = settings.project_path / "audit_report.md"
    if not report_path.exists():
        return web.Response(status=404, text="Report not generated yet.")
        
    return web.FileResponse(report_path)
