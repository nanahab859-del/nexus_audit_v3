from aiohttp import web
from pathlib import Path
from core.atomic import read_json

# ── App version ────────────────────────────────────────────────────────────────
# Read from pyproject.toml if available, otherwise fall back to constant.
def _read_version() -> str:
    try:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject.exists():
            import tomllib  # Python 3.11+
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("version", "3.0.0")
    except Exception:
        pass
    try:
        import importlib.metadata
        return importlib.metadata.version("nexus_audit_v3")
    except Exception:
        pass
    return "3.0.0"   # hard fallback

APP_VERSION = _read_version()


async def get_status(request: web.Request) -> web.Response:
    orchestrator = request.app['orchestrator']
    job = orchestrator.current_job
    if job:
        return web.json_response({
            "state": job.state, "job_id": job.id, "version": APP_VERSION
        })
    return web.json_response({"state": "idle", "job_id": None, "version": APP_VERSION})


async def get_data(request: web.Request) -> web.Response:
    data = await read_json(Path("audit_data_complete.json"))
    if data is None:
        return web.json_response(_EMPTY_DATA_RESPONSE)
    return web.json_response(data)


async def get_capabilities(request: web.Request) -> web.Response:
    from core.models import Category, Severity
    return web.json_response({
        "stacks": [
            "Python", "Go", "JavaScript", "TypeScript",
            "Rust", "Ruby", "Java", "C++", "PHP", "C#"
        ],
        "output_formats": ["JSON", "HTML", "PDF", "Markdown"],
        "severity_levels": [s.value for s in Severity],
        "scanner_categories": [c.value for c in Category],
        "version": APP_VERSION,
        "server_url": request.host,
        "ai_providers": [
            {
                "id": "claude",
                "name": "Claude",
                "requires_key": True,
                "default_model": "claude-opus-4-7",
                "max_tokens_limit": 200000,
                "models": [
                    {"id": "claude-opus-4-7",    "name": "Claude Opus 4.7",    "multimodal": True},
                    {"id": "claude-sonnet-4-5",  "name": "Claude Sonnet 4.5",  "multimodal": True},
                    {"id": "claude-haiku-4-3",   "name": "Claude Haiku 4.3",   "multimodal": False},
                ]
            },
            {
                "id": "gemini",
                "name": "Gemini",
                "requires_key": True,
                "default_model": "gemini-2.5-pro",
                "max_tokens_limit": 128000,
                "models": [
                    {"id": "gemini-2.5-pro",     "name": "Gemini 2.5 Pro",     "multimodal": True},
                    {"id": "gemini-2.5-flash",   "name": "Gemini 2.5 Flash",   "multimodal": True},
                    {"id": "gemini-2.0-flash",   "name": "Gemini 2.0 Flash",   "multimodal": True},
                ]
            },
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "requires_key": False,
                "default_model": "llama3:latest",
                "max_tokens_limit": 4096,
                "models": []   # fetched dynamically from Ollama API
            },
            {
                "id": "custom",
                "name": "Custom Endpoint",
                "requires_key": False,
                "default_model": "",
                "max_tokens_limit": 128000,
                "models": []
            }
        ]
    })


_EMPTY_DATA_RESPONSE = {
    "metadata": {"job_id": None, "project_path": "", "started_at": None,
                 "finished_at": None, "total_findings": 0, "total_violations": 0,
                 "git_context": {}},
    "findings": [],
    "scan_results": [],
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
