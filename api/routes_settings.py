# api/routes_settings.py
from aiohttp import web
from dataclasses import asdict
from core.settings import SettingsManager
from core.security import encrypt, decrypt, is_encrypted

# Whitelist of allowed settings keys to prevent injection of invalid fields
ALLOWED_SETTINGS_KEYS = {
    # Core
    "project_path", "api_key", "ai_enabled", "ai_provider", "ai_model",
    "force_rescan", "scanners", "scanner_configs", "ui",
    # Identity
    "project_name", "project_key", "project_version", "primary_stack",
    "project_description", "project_owner", "project_criticality_tier",
    # Source
    "source_type", "source_remote_url", "source_remote_branch",
    "source_remote_auth_type", "source_remote_token_env", "source_remote_clone_depth",
    # Scope
    "inclusions", "exclusions", "enabled_extensions", "test_pattern", "max_file_size_kb",
    # Context
    "reachability_enabled", "telemetry_source",
    # Reporting
    "output_format", "output_formats", "vex_formats", "include_suppressions",
    "report_output_dir", "report_filename_template", "report_retention_days",
    "custom_metadata",
    # AI Agent
    "ai_remediation_level", "ai_verify_with_tests", "ai_test_command",
    # Integrations
    "webhook_url", "notify_on", "ci_mode", "quality_gate",
    # Environment
    "environment_vars", "secret_refs",
    # Rules
    "custom_rules_yaml",
    # AI Extended
    "ai_temperature", "ai_max_tokens", "ai_timeout", "ai_retry_enabled",
    "ai_max_retries", "ai_custom_endpoint", "ai_api_version", "ai_org_id",
    "ai_local_model", "ai_key_pool", "ai_smart_routing", "ai_fallback_model",
    "ai_budget_cap", "ai_data_scrubber", "ai_prompt_shield",
    "ai_multimodal_enabled", "ai_context_limit",
}

_REDACTED = "***"


async def get_settings(request: web.Request) -> web.Response:
    sm = SettingsManager()
    settings = await sm.load()
    d = asdict(settings)
    # Redact api_key — never send the real value to the browser
    if d.get("api_key"):
        d["api_key"] = _REDACTED
    return web.json_response(d)


async def update_settings(request: web.Request) -> web.Response:
    sm = SettingsManager()
    settings = await sm.load()

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    for key, value in data.items():
        if key not in ALLOWED_SETTINGS_KEYS or not hasattr(settings, key):
            continue

        # Special handling for api_key: encrypt before storing
        if key == "api_key":
            if not value or value == _REDACTED:
                # Skip — empty or sentinel means "don't change"
                continue
            value = encrypt(value)

        setattr(settings, key, value)

    await sm.save()

    # Return the updated settings (redacted)
    d = asdict(settings)
    if d.get("api_key"):
        d["api_key"] = _REDACTED
    return web.json_response(d)


async def get_decrypted_api_key(request: web.Request) -> web.Response:
    """Internal-only endpoint — returns the decrypted API key for orchestrator use."""
    sm = SettingsManager()
    settings = await sm.load()
    raw = settings.api_key or ""
    plaintext = decrypt(raw) if is_encrypted(raw) else raw
    return web.json_response({"api_key": plaintext})
