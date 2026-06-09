# core/config_loader.py
"""
Loads, validates, and merges settings.json with an optional
audit_config.yaml that lives inside the project directory.

YAML wins for any overlapping key (allows per-project overrides
without touching the global settings.json).
"""

from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.settings import SettingsManager


async def load_full_config(
    settings_path: Path = Path("settings.json"),
) -> dict[str, Any]:
    """
    Returns the merged configuration as a plain dict.

    Merge order (later wins):
      settings.json  →  {project_path}/audit_config.yaml
    """
    sm = SettingsManager(settings_path)
    settings = await sm.load()
    config: dict[str, Any] = asdict(settings)

    # Try loading per-project YAML overrides
    project_path = config.get("project_path") or "."
    yaml_path = Path(project_path) / "audit_config.yaml"
    if yaml_path.exists():
        try:
            import yaml  # type: ignore
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
            config = _deep_merge(config, yaml_data)
        except Exception as exc:
            # Warn but don't crash — settings.json is the fallback
            import warnings
            warnings.warn(f"Failed to load audit_config.yaml: {exc}", stacklevel=2)

    return config


def config_to_yaml(config: dict[str, Any]) -> str:
    """Serialize a config dict to a YAML string."""
    try:
        import yaml  # type: ignore
        return yaml.dump(config, default_flow_style=False, allow_unicode=True)
    except ImportError:
        import json
        return f"# pyyaml not installed — falling back to JSON\n{json.dumps(config, indent=2)}"


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Basic structural validation of a config dict.
    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []

    project_path = config.get("project_path", "")
    if not project_path:
        errors.append("project_path is required and cannot be empty.")
    elif not Path(project_path).exists():
        errors.append(f"project_path does not exist: {project_path!r}")

    scanners = config.get("scanners", {})
    if not isinstance(scanners, dict):
        errors.append("scanners must be a dict of {name: bool}.")

    scanner_configs = config.get("scanner_configs", {})
    if not isinstance(scanner_configs, dict):
        errors.append("scanner_configs must be a dict of {name: {key: value}}.")

    ai_enabled = config.get("ai_enabled", False)
    if ai_enabled and not config.get("api_key"):
        errors.append("ai_enabled is True but api_key is not set.")

    return errors


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
