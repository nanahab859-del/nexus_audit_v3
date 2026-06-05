import tempfile
from pathlib import Path
from aiohttp import web

from core.settings import load as load_settings
from core.rules_engine import RulesEngine
from core.dna_builder import build_dna
from core.events import EventBus

async def get_rules(request: web.Request) -> web.Response:
    """GET /api/rules"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    rules_file = settings.project_path / "audit_rules.yaml"
    if not rules_file.exists():
        # Fallback to default_rules.yaml if present in the project root
        rules_file = settings.project_path / "default_rules.yaml"
        if not rules_file.exists():
            return web.json_response({"rules": [], "content": ""})
            
    content = rules_file.read_text(encoding="utf-8")
    engine = RulesEngine(rules_file)
    rules_list = []
    for r in engine.load():
        r_dict = r.__dict__.copy()
        if hasattr(r.severity, "name"):
            r_dict["severity"] = r.severity.name
        if hasattr(r.category, "name"):
            r_dict["category"] = r.category.name
        rules_list.append(r_dict)
            
    return web.json_response({
        "rules": rules_list,
        "content": content
    })

async def post_rules_validate(request: web.Request) -> web.Response:
    """POST /api/rules/validate"""
    try:
        data = await request.json()
        content = data.get("content", "")
    except Exception:
        return web.json_response({"error": "Invalid JSON payload"}, status=400)
        
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = Path(f.name)
        
    try:
        engine = RulesEngine(temp_path)
        errors = engine.validate()
        return web.json_response({"errors": errors})
    finally:
        temp_path.unlink(missing_ok=True)


async def post_rules_save(request: web.Request) -> web.Response:
    """POST /api/rules/save — save rules content"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    try:
        data = await request.json()
        content = data.get("content", "")
    except Exception:
        return web.json_response({"error": "Invalid JSON payload"}, status=400)
    
    # Validate first
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = Path(f.name)
        
    try:
        engine = RulesEngine(temp_path)
        errors = engine.validate()
        if errors:
            return web.json_response({"error": "Validation failed", "errors": errors}, status=400)
    finally:
        temp_path.unlink(missing_ok=True)
    
    # Save to audit_rules.yaml
    rules_file = settings.project_path / "audit_rules.yaml"
    rules_file.write_text(content, encoding="utf-8")
    
    return web.json_response({"ok": True, "saved_to": str(rules_file)})

async def get_rules_evaluate(request: web.Request) -> web.Response:
    """GET /api/rules/evaluate"""
    app = request.app
    settings = load_settings(app["settings_path"])
    
    rules_file = settings.project_path / "audit_rules.yaml"
    if not rules_file.exists():
        rules_file = settings.project_path / "default_rules.yaml"
        
    engine = RulesEngine(rules_file)
    
    bus = EventBus()
    dna = await build_dna(settings.project_path, bus)
    findings = await engine.evaluate(dna, [], bus)
    
    findings_list = []
    for f in findings:
        findings_list.append({
            "scanner": f.scanner,
            "file": f.file,
            "line": f.line,
            "column": f.column,
            "severity": f.severity.name,
            "category": f.category.name,
            "title": f.title,
            "description": f.description,
            "suggestion": f.suggestion,
            "id": f.id
        })
        
    return web.json_response({"findings": findings_list})
