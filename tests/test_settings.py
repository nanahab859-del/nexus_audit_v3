import pytest
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
