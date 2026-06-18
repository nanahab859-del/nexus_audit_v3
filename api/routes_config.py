# api/routes_config.py
"""
Extended configuration endpoints:

  GET  /api/config            — Full merged config (settings.json + audit_config.yaml)
  POST /api/config            — Save config back to settings.json
  GET  /api/config/yaml       — Raw YAML representation of the merged config
  POST /api/config/validate   — Validate config without saving
  GET  /api/scanners/status   — {scanner_name: "installed"|"not_installed"}
  POST /api/scanners/install  — pip-install a scanner; returns SSE-style JSON log lines
  POST /api/scanners/custom   — Register a custom script as a scanner
"""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from aiohttp import web
from dataclasses import asdict

from core.infra.config_loader import load_full_config, config_to_yaml, validate_config
from core.primitives.settings import SettingsManager
from core.infra.registry import PluginRegistry
from core.infra.tool_resolver import (
    is_tool_available, get_tool_version,
    is_tool_available_async, get_tool_version_async,
    TOOL_PIP_PACKAGE,
)
from core.infra.python_exe import _get_venv_python
import sys


SCANNER_CHECKS: dict[str, list[dict]] = {
    "bandit": [
        {"id": "B101", "label": "assert_used"},
        {"id": "B104", "label": "hardcoded_bind_all_interfaces"},
        {"id": "B105", "label": "hardcoded_password_string"},
        {"id": "B106", "label": "hardcoded_password_funcarg"},
        {"id": "B107", "label": "hardcoded_password_default"},
        {"id": "B201", "label": "flask_debug_true"},
        {"id": "B301", "label": "pickle_usage"},
        {"id": "B324", "label": "hashlib_new_insecure_functions"},
    ],
    "vulture": [
        {"id": "V001", "label": "unused_variable"},
        {"id": "V002", "label": "unused_import"},
        {"id": "V003", "label": "unused_function"},
        {"id": "V004", "label": "unused_class"},
        {"id": "V005", "label": "unread_variable"},
    ],
    "semgrep": [],  # semgrep rules come from rulesets, not hardcoded IDs
    "radon":   [],
    "lizard":  [],
    "pylint":  [],
}


# ── /api/config ───────────────────────────────────────────────────────────────

async def get_config(request: web.Request) -> web.Response:
    """Return the fully merged configuration (settings.json + YAML)."""
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    pid = workspace.active_project_id
    if not pid:
        return web.json_response({"error": "No active project"}, status=409)
    config = await load_full_config(sm, pid)
    # Redact api_key
    if config.get("api_key"):
        config["api_key"] = "***"
    return web.json_response(config)


async def save_config(request: web.Request) -> web.Response:
    """Persist an updated configuration to settings.json."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    errors = validate_config(data)
    if errors:
        return web.json_response({"errors": errors}, status=422)

    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    gs = workspace.global_settings
    import dataclasses
    known = {f.name for f in dataclasses.fields(gs.__class__)}
    for key, value in data.items():
        if key in known:
            setattr(gs, key, value)
    workspace.global_settings = gs
    await sm.save_workspace(workspace)
    return web.json_response({"status": "saved"})


# ── /api/config/yaml ─────────────────────────────────────────────────────────

async def get_yaml(request: web.Request) -> web.Response:
    """Return the merged config as a YAML text document."""
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    pid = workspace.active_project_id
    if not pid:
        return web.json_response({"error": "No active project"}, status=409)
    config = await load_full_config(sm, pid)
    if config.get("api_key"):
        config["api_key"] = "***"
    yaml_text = config_to_yaml(config)
    return web.Response(text=yaml_text, content_type="text/plain")


# ── /api/config/validate ─────────────────────────────────────────────────────

async def validate_config_endpoint(request: web.Request) -> web.Response:
    """Validate a config dict without saving. Returns errors list."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    errors = validate_config(data)
    return web.json_response({"valid": len(errors) == 0, "errors": errors})


# ── /api/config/sync_identity ────────────────────────────────────────────────

async def sync_identity(request: web.Request) -> web.Response:
    """Dynamically read the project's identity from local files (pyproject.toml, package.json)."""
    import json
    try:
        import tomllib
    except ImportError:
        tomllib = None

    identity = {"project_name": None, "project_version": None, "primary_stack": None}

    # Try pyproject.toml
    pyproject = Path("pyproject.toml")
    if pyproject.exists() and tomllib:
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
                proj = data.get("project", {})
                if proj.get("name"): identity["project_name"] = proj["name"]
                if proj.get("version"): identity["project_version"] = proj["version"]
                identity["primary_stack"] = "Python"
        except Exception: pass

    # Try package.json
    package_json = Path("package.json")
    if package_json.exists() and not identity["project_name"]:
        try:
            with open(package_json, "r") as f:
                data = json.load(f)
                if data.get("name"): identity["project_name"] = data["name"]
                if data.get("version"): identity["project_version"] = data["version"]
                identity["primary_stack"] = "JavaScript"
        except Exception: pass

    return web.json_response(identity)


# ── /api/scanners ─────────────────────────────────────────────────────────────

async def get_scanners(request: web.Request) -> web.Response:
    """
    Returns a list of registered scanners dynamically discovered from plugins/.
    Uses asyncio.gather to check all tool statuses in parallel — fast.
    """
    # Use the shared registry from app state if available, else create one
    registry: PluginRegistry = request.app.get('registry') or PluginRegistry(Path("plugins"))
    if not registry._loaded:
        registry.load()

    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    custom_meta = (workspace.global_settings.ui or {}).get("custom_scanners", {})

    scanner_classes = registry.all()

    # Async parallel tool availability checks
    async def _check_scanner(scanner_class) -> dict:
        name = scanner_class.name
        tool_cmd = TOOL_PIP_PACKAGE.get(name, name)
        installed = await is_tool_available_async(tool_cmd)
        version = await get_tool_version_async(tool_cmd) if installed else None
        desc_raw = scanner_class.__doc__ or name.title()
        desc = desc_raw.strip().splitlines()[0]
        cat_raw = getattr(scanner_class, 'category', None)
        category = getattr(cat_raw, 'value', str(cat_raw or 'Other')).title()
        languages = getattr(scanner_class, 'languages', ['*'])
        pip_pkg = TOOL_PIP_PACKAGE.get(name, name)
        return {
            "name": name,
            "category": category,
            "badge": desc[:20],
            "languages": languages,
            "description": desc,
            "status": "installed" if installed else "not_installed",
            "version": version,
            "pip_package": pip_pkg,
            "checks": SCANNER_CHECKS.get(name, []),
        }

    results = await asyncio.gather(*[_check_scanner(sc) for sc in scanner_classes])
    result = list(results)

    # Append custom scanners (no subprocess needed — just check file exists)
    for custom_name, custom_info in custom_meta.items():
        exe = custom_info.get("executable", "")
        installed = Path(exe).exists() if exe else False
        result.append({
            "name": custom_name,
            "category": "Custom",
            "badge": "Custom Plugin",
            "languages": ["*"],
            "description": f"Custom executable: {exe}",
            "status": "installed" if installed else "not_installed",
            "version": None,
            "pip_package": None,
            "custom": True,
            "executable": exe,
        })

    return web.json_response(result)


# ── /api/registry/reload ──────────────────────────────────────────────────────

async def reload_registry(request: web.Request) -> web.Response:
    """
    Clears and re-scans the plugins/ directory.
    Lets the user drop a new .py plugin file and pick it up without a restart.
    """
    registry: PluginRegistry = request.app.get('registry') or PluginRegistry(Path("plugins"))
    registry._registry.clear()
    registry._loaded = False
    registry.load()
    return web.json_response({
        "status": "reloaded",
        "scanners": registry.names(),
    })


# ── /api/scanners/status ─────────────────────────────────────────────────────

# Canonical mapping: scanner name → tool executable name
_SCANNER_TOOL_MAP: dict[str, str] = {
    "vulture":         "vulture",
    "bandit":          "bandit",
    "radon":           "radon",
    "pylint":          "pylint",
    "semgrep":         "semgrep",
    "pip-audit":       "pip-audit",
    "npm-audit":       "npm",       # npm-audit is part of npm
    "lizard":          "lizard",
    "django_settings": "python",    # always available if Python is
}

async def get_scanners_status(request: web.Request) -> web.Response:
    """
    Returns:
        {
          "vulture":   {"status": "installed",     "version": "2.11"},
          "semgrep":   {"status": "not_installed",  "version": null},
          ...
        }
    """
    # Fix 18: use shared registry from app state — don't create a new one per call
    registry: PluginRegistry = request.app.get('registry') or PluginRegistry(Path("plugins"))
    if not registry._loaded:
        registry.load()
    registered = set(registry.names())

    # Fetch custom scanners from workspace.global_settings
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    custom = (workspace.global_settings.ui or {}).get("custom_scanners", {})

    result: dict[str, dict] = {}

    # Known scanners
    for scanner_name, tool_cmd in _SCANNER_TOOL_MAP.items():
        installed = is_tool_available(tool_cmd)
        version = get_tool_version(tool_cmd) if installed else None
        has_plugin = scanner_name in registered
        result[scanner_name] = {
            "status":     "installed" if installed else "not_installed",
            "version":    version,
            "has_plugin": has_plugin,
            "pip_package": TOOL_PIP_PACKAGE.get(scanner_name),
        }

    # Custom scanners
    for name, meta in custom.items():
        exe = meta.get("executable", "")
        installed = Path(exe).exists() if exe else False
        result[name] = {
            "status":     "installed" if installed else "not_installed",
            "version":    None,
            "has_plugin": name in registered,
            "pip_package": None,
            "custom":     True,
            "executable": exe,
        }

    return web.json_response(result)


# ── /api/scanners/install ────────────────────────────────────────────────────

async def install_scanner(request: web.Request) -> web.Response:
    """
    Install a scanner via pip.  Streams install output as JSON-lines:
        {"line": "...", "done": false}
        {"line": "Done", "done": true, "status": "ok"|"error"}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return web.json_response({"error": "name is required"}, status=400)

    pip_pkg = TOOL_PIP_PACKAGE.get(name) or name
    venv_python = _get_venv_python()
    python_exe = str(venv_python) if (venv_python and venv_python.exists()) else sys.executable

    # Build pip install command
    cmd = [python_exe, "-m", "pip", "install", "--upgrade", pip_pkg]

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "application/x-ndjson"},
    )
    await response.prepare(request)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def _stream():
            assert proc.stdout
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                payload = json.dumps({"line": line, "done": False}) + "\n"
                await response.write(payload.encode())

        await asyncio.wait_for(_stream(), timeout=300)
        await proc.wait()
        status = "ok" if proc.returncode == 0 else "error"
        final = json.dumps({"line": "", "done": True, "status": status}) + "\n"
        await response.write(final.encode())

    except asyncio.TimeoutError:
        final = json.dumps({"line": "Timed out", "done": True, "status": "error"}) + "\n"
        await response.write(final.encode())
    except Exception as exc:
        final = json.dumps({"line": str(exc), "done": True, "status": "error"}) + "\n"
        await response.write(final.encode())

    await response.write_eof()
    return response


# ── /api/scanners/custom ─────────────────────────────────────────────────────

async def register_custom_scanner(request: web.Request) -> web.Response:
    """
    Register a custom script/executable as a named scanner.
    Stores entry in settings.ui.custom_scanners[name].
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    name = data.get("name", "").strip()
    executable = data.get("executable", "").strip()
    output_pattern = data.get("output_pattern", "")

    if not name:
        return web.json_response({"error": "name is required"}, status=400)
    if not executable:
        return web.json_response({"error": "executable is required"}, status=400)
    if not Path(executable).exists():
        return web.json_response(
            {"error": f"Executable not found: {executable}"}, status=400
        )

    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    gs = workspace.global_settings
    if not isinstance(gs.ui, dict):
        gs.ui = {}
    if "custom_scanners" not in gs.ui:
        gs.ui["custom_scanners"] = {}

    gs.ui["custom_scanners"][name] = {
        "executable":     executable,
        "output_pattern": output_pattern,
    }
    workspace.global_settings = gs
    await sm.save_workspace(workspace)
    return web.json_response({"status": "registered", "name": name})


async def delete_custom_scanner(request: web.Request) -> web.Response:
    """
    DELETE /api/scanners/custom/{name}
    Remove a custom scanner registration from settings.ui.custom_scanners.
    """
    name = request.match_info.get("name", "").strip()
    if not name:
        return web.json_response({"error": "name is required"}, status=400)

    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    gs = workspace.global_settings
    custom = (gs.ui or {}).get("custom_scanners", {})
    if name not in custom:
        return web.json_response({"error": f"Custom scanner '{name}' not found"}, status=404)

    del custom[name]
    if isinstance(gs.ui, dict):
        gs.ui["custom_scanners"] = custom
    workspace.global_settings = gs
    await sm.save_workspace(workspace)
    return web.json_response({"status": "deleted", "name": name})


# ── /api/vex ─────────────────────────────────────────────────────────────────

async def get_vex(request: web.Request) -> web.Response:
    """GET /api/vex — Return current VEX suppressions from settings."""
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    vex = (workspace.global_settings.ui or {}).get("vex_suppressions", [])
    return web.json_response({"suppressions": vex})


async def delete_vex(request: web.Request) -> web.Response:
    """DELETE /api/vex — Clear all VEX suppressions."""
    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    gs = workspace.global_settings
    if isinstance(gs.ui, dict):
        gs.ui["vex_suppressions"] = []
    workspace.global_settings = gs
    await sm.save_workspace(workspace)
    return web.json_response({"status": "cleared"})


async def upload_vex(request: web.Request) -> web.Response:
    """
    POST /api/vex/upload — Upload a VEX file (JSON or CycloneDX-VEX format).
    Parses suppression entries and merges them into settings.ui.vex_suppressions.
    """
    try:
        reader = await request.multipart()
        field = await reader.next()
        if field is None:
            return web.json_response({"error": "No file uploaded"}, status=400)
        raw = await field.read(decode=True)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"Invalid JSON in VEX file: {e}"}, status=400)
    except Exception as e:
        return web.json_response({"error": f"Upload failed: {e}"}, status=400)

    # Accept CycloneDX VEX: {"vulnerabilities": [...]} or plain [...]
    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("vulnerabilities", data.get("suppressions", []))

    sm: SettingsManager = request.app['sm']
    workspace = await sm.load_workspace()
    gs = workspace.global_settings
    if not isinstance(gs.ui, dict):
        gs.ui = {}
    existing = gs.ui.get("vex_suppressions", [])
    # De-duplicate by ID if present
    existing_ids = {e.get("id") for e in existing if isinstance(e, dict) and e.get("id")}
    new_entries = [e for e in entries if not (isinstance(e, dict) and e.get("id") in existing_ids)]
    gs.ui["vex_suppressions"] = existing + new_entries
    workspace.global_settings = gs
    await sm.save_workspace(workspace)
    return web.json_response({
        "status": "imported",
        "added": len(new_entries),
        "total": len(gs.ui["vex_suppressions"]),
    })

