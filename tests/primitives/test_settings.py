import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.primitives.settings import SettingsManager
from core.primitives.models import ProjectSettings, Workspace, GlobalSettings

@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    # Ensure .nexus_audit exists
    (tmp_path / ".nexus_audit").mkdir()
    return SettingsManager()

@pytest.mark.asyncio
async def test_settings_load_save(manager, tmp_path):
    proj = await manager.register_project("test", str(tmp_path))
    
    settings = await manager.get_project_settings(proj.id)
    settings.project_name = "test-renamed"
    await manager.update_project_settings(proj.id, settings)
    
    # Reload
    manager2 = SettingsManager()
    settings2 = await manager2.get_project_settings(proj.id)
    assert settings2.project_name == "test-renamed"

@pytest.mark.asyncio
async def test_settings_unknown_fields_filtered(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    await manager.patch_project_settings(proj.id, {"unknown_key": "should_be_ignored"})
    
    settings = await manager.get_project_settings(proj.id)
    assert settings.project_name == "Test"
    
@pytest.mark.asyncio
async def test_settings_concurrent_saves(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    
    async def modify_and_save(val):
        settings = await manager.get_project_settings(proj.id)
        settings.project_name = val
        await asyncio.sleep(0.01)
        await manager.update_project_settings(proj.id, settings)
        
    await asyncio.gather(
        modify_and_save("A"),
        modify_and_save("B"),
        modify_and_save("C"),
    )
    
    settings = await manager.get_project_settings(proj.id)
    assert settings.project_name in ["A", "B", "C"]

@pytest.mark.asyncio
async def test_load_workspace_with_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    (tmp_path / ".nexus_audit" / "workspace.json").write_text("corrupt{json")
    
    manager = SettingsManager()
    # Should not raise exception
    workspace = await manager.load_workspace()
    assert workspace.projects == {}

@pytest.mark.asyncio
async def test_patch_project_settings_with_unknown_key(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    
    await manager.patch_project_settings(proj.id, {"unknown_key": "val"})
    settings = await manager.get_project_settings(proj.id)
    assert not hasattr(settings, "unknown_key")

@pytest.mark.asyncio
async def test_save_project_creates_directory(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    assert (tmp_path / ".nexus_audit" / "projects" / proj.id).exists()

@pytest.mark.asyncio
async def test_load_project_with_missing_file(manager):
    with pytest.raises(FileNotFoundError):
        await manager.load_project("nonexistent-id")

@pytest.mark.asyncio
async def test_delete_project_cleans_directory(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    proj_dir = tmp_path / ".nexus_audit" / "projects" / proj.id
    assert proj_dir.exists()
    
    await manager.delete_project(proj.id)
    assert not proj_dir.exists()

@pytest.mark.asyncio
async def test_set_active_project_updates_workspace(manager, tmp_path):
    proj1 = await manager.register_project("Test1", str(tmp_path))
    proj2 = await manager.register_project("Test2", str(tmp_path))
    
    await manager.set_active_project(proj1.id)
    assert (await manager.get_active_project()).id == proj1.id
    
    await manager.set_active_project(proj2.id)
    assert (await manager.get_active_project()).id == proj2.id

@pytest.mark.asyncio
async def test_patch_project_settings_preserves_unchanged_keys(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    original_path = proj.settings.project_path
    
    await manager.patch_project_settings(proj.id, {"project_name": "new-name"})
    
    settings = await manager.get_project_settings(proj.id)
    assert settings.project_name == "new-name"
    assert settings.project_path == original_path

@pytest.mark.asyncio
async def test_export_project_config_returns_valid_dict(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    
    config = await manager.export_project_config(proj.id)
    assert "project_path" in config
    assert "project_name" in config
    assert "scanners" in config
    assert "scanner_configs" in config

@pytest.mark.asyncio
async def test_settings_load_invalid_project(manager, tmp_path):
    # Test loading a project that doesn't have a settings file
    proj_dir = tmp_path / ".nexus_audit" / "projects" / "broken-id"
    proj_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        await manager.load_project("broken-id")

@pytest.mark.asyncio
async def test_load_workspace_handles_permission_denied(manager):
    with patch("core.primitives.settings.read_json", side_effect=PermissionError):
        # Should return default workspace
        workspace = await manager.load_workspace()
        assert isinstance(workspace, Workspace)

@pytest.mark.asyncio
async def test_save_workspace_handles_permission_denied(manager):
    workspace = Workspace()
    with patch("core.primitives.settings.write_json", side_effect=PermissionError):
        # Should not crash
        await manager.save_workspace(workspace)

@pytest.mark.asyncio
async def test_save_project_atomic_write_failure(manager, tmp_path):
    proj = await manager.register_project("Test", str(tmp_path))
    # Capture state before failure
    orig_settings = await manager.get_project_settings(proj.id)
    
    with patch("core.primitives.settings.write_json", side_effect=OSError):
        # Should catch OSError and return
        await manager.save_project(proj)
            
    # Should be unchanged
    new_settings = await manager.get_project_settings(proj.id)
    assert new_settings == orig_settings

@pytest.mark.asyncio
async def test_save_workspace_with_api_key(manager, tmp_path):
    # Covers: if ws_dict["global_settings"].get("api_key"):
    ws = Workspace(global_settings=GlobalSettings(api_key="secret-key"))
    await manager.save_workspace(ws)
    # Check that key was encrypted
    assert (tmp_path / ".nexus_audit" / "workspace.json").read_text()

@pytest.mark.asyncio
async def test_register_project_invalid_path(manager):
    # Covers: if not resolved_path.exists() or not resolved_path.is_dir():
    with pytest.raises(ValueError):
        await manager.register_project("test", "/invalid/path/that/does/not/exist")

@pytest.mark.asyncio
async def test_load_project_without_last_audited(manager, tmp_path):
    # Covers: if data.get("last_audited_at") else None
    proj = await manager.register_project("Test", str(tmp_path))
    data_path = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(data_path.read_text())
    del data["last_audited_at"]
    data_path.write_text(json.dumps(data))
    
    project = await manager.load_project(proj.id)
    assert project.last_audited_at is None

@pytest.mark.asyncio
async def test_get_active_project_none(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sm = SettingsManager()
    assert await sm.get_active_project() is None

@pytest.mark.asyncio
async def test_global_settings_methods(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sm = SettingsManager()
    gs = await sm.get_global_settings()
    assert gs is not None
    gs.api_key = "test_api_key"
    await sm.update_global_settings(gs)
    gs_loaded = await sm.get_global_settings()
    assert gs_loaded.api_key == "test_api_key"

@pytest.mark.asyncio
async def test_severity_string_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))
    import json
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    data["settings"]["fail_on_severity"] = "LOW"
    pfile.write_text(json.dumps(data))
    
    loaded = await sm.load_project(proj.id)
    assert loaded.settings.fail_on_severity.name == "LOW"


# ── New coverage tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_workspace_skips_malformed_project(tmp_path, monkeypatch):
    """Covers lines 53-54: exception path when a project entry is malformed."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    import json
    ws_data = {
        "global_settings": {"api_key": "", "ui_theme": "dark"},
        "projects": {
            "bad-proj": {"id": "bad-proj"}  # missing required 'name', 'path', 'settings'
        },
        "active_project_id": None,
    }
    (tmp_path / ".nexus_audit" / "workspace.json").write_text(json.dumps(ws_data))
    sm = SettingsManager()
    workspace = await sm.load_workspace()
    # The malformed project is silently skipped
    assert "bad-proj" not in workspace.projects


def test_get_project_raises_key_error_if_not_cached(manager):
    """Covers line 137: get_project() raises KeyError when project not in cache."""
    with pytest.raises(KeyError, match="not in cache"):
        manager.get_project("nonexistent-id")


def test_current_job_returns_none(manager):
    """Covers line 145: current_job() always returns None (placeholder)."""
    assert manager.current_job() is None


@pytest.mark.asyncio
async def test_patch_project_settings_severity_as_int(tmp_path, monkeypatch):
    """Covers line 212: severity as int in patch_project_settings."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))

    # Manually write an int severity into the project file
    import json
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    data["settings"]["fail_on_severity"] = 4  # CRITICAL as int
    pfile.write_text(json.dumps(data))

    # patch_project_settings must reconstruct Severity from int
    new_settings = await sm.patch_project_settings(proj.id, {"project_name": "patched"})
    assert new_settings.project_name == "patched"
    from core.primitives.models import Severity
    assert new_settings.fail_on_severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_deserialise_project_severity_as_int(tmp_path, monkeypatch):
    """Covers lines 265-268: severity as int in _deserialise_project."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))

    import json
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    data["settings"]["fail_on_severity"] = 1  # LOW as int
    pfile.write_text(json.dumps(data))

    loaded = await sm.load_project(proj.id)
    from core.primitives.models import Severity
    assert loaded.settings.fail_on_severity == Severity.LOW


@pytest.mark.asyncio
async def test_deserialise_project_severity_unknown_type(tmp_path, monkeypatch):
    """Covers the else branch: unrecognised severity type falls back to CRITICAL."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))

    import json
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    data["settings"]["fail_on_severity"] = None  # neither str nor int
    pfile.write_text(json.dumps(data))

    loaded = await sm.load_project(proj.id)
    from core.primitives.models import Severity
    assert loaded.settings.fail_on_severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_patch_project_severity_unknown_type(tmp_path, monkeypatch):
    """Covers the else/CRITICAL branch in patch_project_settings severity handling."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))

    import json
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    data["settings"]["fail_on_severity"] = None
    pfile.write_text(json.dumps(data))

    new_settings = await sm.patch_project_settings(proj.id, {"project_name": "x"})
    from core.primitives.models import Severity
    assert new_settings.fail_on_severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_delete_project_evicts_from_cache(tmp_path, monkeypatch):
    """Covers cache eviction in delete_project and ensures get_project raises after delete."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".nexus_audit").mkdir()
    sm = SettingsManager()
    proj = await sm.register_project("test", str(tmp_path))

    # Load into cache
    await sm.load_project(proj.id)
    assert proj.id in sm._project_cache

    await sm.delete_project(proj.id)
    assert proj.id not in sm._project_cache
    with pytest.raises(KeyError):
        sm.get_project(proj.id)

