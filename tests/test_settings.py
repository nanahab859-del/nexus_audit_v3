import pytest
from pathlib import Path
from core.settings import (
    load,
    save,
    DEFAULT_SETTINGS,
    SettingsValidationError,
)
from core.models import Settings
import json


def test_load_missing_file() -> None:
    """Test loading missing file returns DEFAULT_SETTINGS."""
    result = load(Path("/nonexistent/settings.json"))
    assert result.project_path == DEFAULT_SETTINGS.project_path
    assert result.ai_enabled == DEFAULT_SETTINGS.ai_enabled


def test_load_valid_file(tmp_path: Path) -> None:
    """Test loading valid settings file."""
    settings_file = tmp_path / "settings.json"
    settings_data = {
        "project_path": ".",
        "scanners": {"bandit": True},
    }
    settings_file.write_text(json.dumps(settings_data))

    result = load(settings_file)
    assert isinstance(result, Settings)
    assert result.scanners == {"bandit": True}


def test_load_invalid_schema(tmp_path: Path) -> None:
    """Test that invalid schema raises SettingsValidationError."""
    settings_file = tmp_path / "settings.json"
    # Missing required 'scanners' field
    settings_data = {"project_path": "."}
    settings_file.write_text(json.dumps(settings_data))

    with pytest.raises(SettingsValidationError):
        load(settings_file)


@pytest.mark.asyncio
async def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Test save → load round-trip preserves all fields."""
    settings = Settings(
        project_path=tmp_path,
        api_key="test-key",
        ai_enabled=True,
        ai_provider="gemini",
        ai_model="test-model",
        force_rescan=True,
        scanners={"bandit": True, "vulture": False},
        scanner_configs={"bandit": {"level": "high"}},
        ui={"theme": "dark"},
    )

    settings_file = tmp_path / "settings.json"
    await save(settings, settings_file)
    result = load(settings_file)

    assert result.api_key == settings.api_key
    assert result.ai_enabled == settings.ai_enabled
    assert result.ai_provider == settings.ai_provider
    assert result.ai_model == settings.ai_model
    assert result.force_rescan == settings.force_rescan
    assert result.scanners == settings.scanners
    assert result.scanner_configs == settings.scanner_configs
    assert result.ui == settings.ui


def test_load_relative_path_resolution(tmp_path: Path) -> None:
    """Test that relative project_path is resolved."""
    settings_file = tmp_path / "settings.json"
    settings_data = {
        "project_path": "subdir",
        "scanners": {},
    }
    settings_file.write_text(json.dumps(settings_data))

    result = load(settings_file)
    assert result.project_path.is_absolute()


def test_load_absolute_path_preserved(tmp_path: Path) -> None:
    """Test that absolute project_path is preserved."""
    settings_file = tmp_path / "settings.json"
    abs_path = tmp_path / "myproject"
    settings_data = {
        "project_path": str(abs_path),
        "scanners": {},
    }
    settings_file.write_text(json.dumps(settings_data))

    result = load(settings_file)
    assert result.project_path == abs_path


@pytest.mark.asyncio
async def test_save_creates_formatted_json(tmp_path: Path) -> None:
    """Test that save creates properly formatted JSON."""
    settings = Settings(
        project_path=tmp_path,
        scanners={"test": True},
    )

    settings_file = tmp_path / "settings.json"
    await save(settings, settings_file)

    content = settings_file.read_text()
    assert "\n" in content  # Should have newlines
    assert "project_path" in content
    assert "scanners" in content
