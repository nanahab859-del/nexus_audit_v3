import pytest
import asyncio
import json
from pathlib import Path
from core.settings import SettingsManager
from core.models import Settings

@pytest.mark.asyncio
async def test_settings_load_save(tmp_path):
    path = tmp_path / "settings.json"
    manager = SettingsManager(path=path)
    
    settings = await manager.load()
    assert settings.project_path == str(Path.cwd())
    
    settings.api_key = "test-key"
    await manager.save()
    
    manager2 = SettingsManager(path=path)
    settings2 = await manager2.load()
    assert settings2.api_key == "test-key"

@pytest.mark.asyncio
async def test_settings_unknown_fields_filtered(tmp_path):
    path = tmp_path / "settings.json"
    
    # Write raw JSON with invalid keys
    with open(path, "w") as f:
        json.dump({
            "project_path": "/test/path",
            "project_name": "Test",
            "invalid_key": "should_be_dropped",
            "ui": {"custom_scanners": {}, "unknown_ui_key": True}
        }, f)
        
    manager = SettingsManager(path=path)
    settings = await manager.load()
    
    assert settings.project_name == "Test"
    assert not hasattr(settings, "invalid_key")
    
    # Save back and verify the file no longer contains invalid_key
    await manager.save()
    with open(path, "r") as f:
        data = json.load(f)
    
    assert "invalid_key" not in data

@pytest.mark.asyncio
async def test_settings_concurrent_saves(tmp_path):
    """Test that asyncio.Lock prevents race conditions during save/load"""
    path = tmp_path / "settings.json"
    manager = SettingsManager(path=path)
    
    async def modify_and_save(val):
        settings = await manager.load()
        settings.project_name = val
        # yield control to simulate concurrency
        await asyncio.sleep(0.01)
        await manager.save()
        
    # Launch multiple concurrent saves
    await asyncio.gather(
        modify_and_save("A"),
        modify_and_save("B"),
        modify_and_save("C"),
    )
    
    # Verify file is not corrupted and contains one of the final values
    settings = await manager.load()
    assert settings.project_name in ["A", "B", "C"]
