import json
from pathlib import Path
from typing import Any

import jsonschema

from core.atomic import write_json
from core.models import Settings


class SettingsValidationError(ValueError):
    """Raised when settings validation fails."""
    pass


DEFAULT_SETTINGS = Settings(
    project_path=Path("."),
    api_key=None,
    ai_enabled=False,
    ai_provider="claude",
    ai_model="claude-opus-4-7",
    force_rescan=False,
    scanners={},
    scanner_configs={},
    ui={},
)


def load(path: Path = Path("settings.json")) -> Settings:
    """
    Load settings from JSON file.
    If file missing, return DEFAULT_SETTINGS.
    If file present, validate against schema and return Settings.
    Raises SettingsValidationError on validation failure.
    """
    if not path.exists():
        return DEFAULT_SETTINGS

    with open(path, "r") as f:
        data = json.load(f)

    schema_path = Path(__file__).parent.parent / "settings.schema.json"
    with open(schema_path, "r") as f:
        schema = json.load(f)

    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise SettingsValidationError(f"Settings validation failed: {e.message}") from e

    # Convert project_path to absolute Path
    project_path_str = data.get("project_path", ".")
    project_path = Path(project_path_str)
    if not project_path.is_absolute():
        project_path = (path.parent / project_path).resolve()

    return Settings(
        project_path=project_path,
        api_key=data.get("api_key"),
        ai_enabled=data.get("ai_enabled", False),
        ai_provider=data.get("ai_provider", "claude"),
        ai_model=data.get("ai_model", "claude-opus-4-7"),
        force_rescan=data.get("force_rescan", False),
        scanners=data.get("scanners", {}),
        scanner_configs=data.get("scanner_configs", {}),
        ui=data.get("ui", {}),
    )


async def save(settings: Settings, path: Path = Path("settings.json")) -> None:
    """Serialize Settings to dict and write atomically."""
    data: dict[str, Any] = {
        "project_path": str(settings.project_path),
        "api_key": settings.api_key,
        "ai_enabled": settings.ai_enabled,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "force_rescan": settings.force_rescan,
        "scanners": settings.scanners,
        "scanner_configs": settings.scanner_configs,
        "ui": settings.ui,
    }
    await write_json(path, data)
