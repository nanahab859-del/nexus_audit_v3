import os
import yaml
import logging
from typing import Any, Optional
from pathlib import Path
from core.primitives.models import GlobalSettings, ProjectSettings, Severity, ConfigurationError, to_dict
from core.primitives.settings import SettingsManager

logger = logging.getLogger(__name__)

def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

async def load_full_config(
    settings_manager: SettingsManager,
    project_id: str,
    global_overrides: Optional[dict] = None
) -> dict:
    # 1-4. Base config from SettingsManager
    ws = await settings_manager.load_workspace()
    gs = ws.global_settings
    proj = await settings_manager.load_project(project_id)
    ps = proj.settings

    # Build base dict
    config = deep_merge(to_dict(gs), to_dict(ps))

    # 6. YAML override
    yaml_path = Path(proj.path) / ".nexus-audit.yaml"
    if yaml_path.exists():
        try:
            with open(yaml_path, "r") as f:
                yaml_data = yaml.safe_load(f) or {}
            
            whitelist = {
                "scanners", "scanner_configs", "ignore_paths", 
                "fail_on_severity", "force_rescan", "quality_gate"
            }
            
            cleaned_yaml = {}
            for k, v in yaml_data.items():
                if k in whitelist:
                    cleaned_yaml[k] = v
                else:
                    logger.warning(f"Ignored key in .nexus-audit.yaml: {k}")
            
            config = deep_merge(config, cleaned_yaml)
        except Exception as e:
            logger.warning(f"Failed to load .nexus-audit.yaml: {e}")

    # 7. Environment overrides
    env_overrides = {}
    for env_key, value in os.environ.items():
        if env_key.startswith("NEXUS_"):
            key = env_key[6:].lower()
            
            # Type conversion
            if value.lower() == "true":
                converted_value = True
            elif value.lower() == "false":
                converted_value = False
            else:
                try:
                    if "." in value:
                        converted_value = float(value)
                    else:
                        converted_value = int(value)
                except ValueError:
                    converted_value = value
            env_overrides[key] = converted_value
    
    config = deep_merge(config, env_overrides)

    # 8. Global overrides
    if global_overrides:
        config = deep_merge(config, global_overrides)

    # 9. Validate
    errors = validate_config(config)
    if errors:
        raise ConfigurationError(errors)

    return config

def validate_config(config: dict) -> list[str]:
    errors = []
    if not config.get("project_path"):
        errors.append("project_path is required")
        
    scanners = config.get("scanners", {})
    if not isinstance(scanners, dict):
        errors.append("scanners must be a dictionary")
    else:
        for k, v in scanners.items():
            if not isinstance(v, bool):
                errors.append(f"scanners.{k} must be a boolean, got {type(v).__name__}")
                
    fail_on = config.get("fail_on_severity")
    valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
    
    # Handle both Enum name or raw string, or integer value
    if isinstance(fail_on, Severity):
        fail_on_val = fail_on.name
    elif isinstance(fail_on, int):
        try:
            fail_on_val = Severity(fail_on).name
        except ValueError:
            fail_on_val = str(fail_on)
    else:
        fail_on_val = str(fail_on).upper() if fail_on else None
        
    if fail_on and fail_on_val not in valid_severities:
        errors.append(f"fail_on_severity must be one of {valid_severities}, got: {fail_on_val}")
        
    qg = config.get("quality_gate", {})
    if not isinstance(qg, dict):
        errors.append("quality_gate must be a dictionary")
    else:
        for field in ["max_critical", "max_high"]:
            if field in qg and (not isinstance(qg[field], int) or qg[field] < 0):
                errors.append(f"quality_gate.{field} must be a non-negative integer")
        for field in ["min_fleet_score", "min_cvss_threshold"]:
            if field in qg and (not isinstance(qg[field], (int, float)) or qg[field] < 0):
                errors.append(f"quality_gate.{field} must be a non-negative number")

    # Scanner configs validation
    scanner_configs = config.get("scanner_configs", {})
    if not isinstance(scanner_configs, dict):
        errors.append("scanner_configs must be a dictionary")
        
    return errors
