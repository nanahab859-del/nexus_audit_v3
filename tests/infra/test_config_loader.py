import os
import pytest
import asyncio
import logging
import yaml
from pathlib import Path
from core.primitives.settings import SettingsManager
from core.primitives.models import Severity
from core.infra.config_loader import load_full_config, ConfigurationError, validate_config, deep_merge

def test_deep_merge():
    base = {"a": {"b": 1}, "c": 2}
    override = {"a": {"d": 3}, "c": 4}
    res = deep_merge(base, override)
    assert res == {"a": {"b": 1, "d": 3}, "c": 4}

@pytest.mark.asyncio
async def test_merge_order(tmp_path):
    sm = SettingsManager()
    gs = await sm.get_global_settings()
    gs.ai_provider = "default-claude"
    await sm.update_global_settings(gs)
    proj = await sm.register_project("test-project", str(tmp_path))
    
    yaml_path = tmp_path / ".nexus-audit.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({"fail_on_severity": "HIGH", "ai_provider": "tamper-claude"}, f)
        
    os.environ["NEXUS_FORCE_RESCAN"] = "true"
    
    config = await load_full_config(sm, proj.id)
    assert config["fail_on_severity"] in ("HIGH", 4)
    assert config["force_rescan"] is True
    assert config["ai_provider"] == "default-claude" # Ignored by whitelist
    
    del os.environ["NEXUS_FORCE_RESCAN"]
    await sm.delete_project(proj.id)

@pytest.mark.asyncio
async def test_yaml_whitelist_and_exception(tmp_path, monkeypatch):
    sm = SettingsManager()
    proj = await sm.register_project("test-project", str(tmp_path))
    
    yaml_path = tmp_path / ".nexus-audit.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({"ai_provider": "claude"}, f)
        
    await load_full_config(sm, proj.id)
    
    # Exception handling
    yaml_path.touch(mode=0o000)
    # Just to be sure, we mock open
    def mock_open(*args, **kwargs): raise PermissionError("no read")
    monkeypatch.setattr("builtins.open", mock_open)
    
    await load_full_config(sm, proj.id)
    
    await sm.delete_project(proj.id)

@pytest.mark.asyncio
async def test_env_parsing(tmp_path):
    sm = SettingsManager()
    proj = await sm.register_project("test-project", str(tmp_path))
    
    os.environ["NEXUS_A"] = "False"
    os.environ["NEXUS_B"] = "3.14"
    os.environ["NEXUS_C"] = "not_a_num"
    os.environ["NEXUS_D"] = "10"
    
    config = await load_full_config(sm, proj.id)
    assert config["a"] is False
    assert config["b"] == 3.14
    assert config["c"] == "not_a_num"
    assert config["d"] == 10
    
    del os.environ["NEXUS_A"]
    del os.environ["NEXUS_B"]
    del os.environ["NEXUS_C"]
    del os.environ["NEXUS_D"]
    await sm.delete_project(proj.id)

def test_validation():
    def assert_error(msg, errors):
        assert any(msg in err for err in errors), f"Expected '{msg}' in {errors}"

    # missing project_path
    assert_error("project_path is required", validate_config({}))
    
    # scanners dict check
    assert_error("scanners must be a dictionary", validate_config({"project_path": "x", "scanners": "invalid"}))
    assert_error("scanners.a must be a boolean", validate_config({"project_path": "x", "scanners": {"a": "yes"}}))
    
    # fail_on_severity checks
    assert not validate_config({"project_path": "x", "fail_on_severity": Severity.HIGH})
    assert not validate_config({"project_path": "x", "fail_on_severity": 3}) # LOW
    assert_error("fail_on_severity must be one of", validate_config({"project_path": "x", "fail_on_severity": 99}))
    assert_error("fail_on_severity must be one of", validate_config({"project_path": "x", "fail_on_severity": "INVALID"}))
    
    # quality_gate dict check
    assert_error("quality_gate must be a dictionary", validate_config({"project_path": "x", "quality_gate": "invalid"}))
    assert_error("quality_gate.max_critical must be a non-negative integer", validate_config({"project_path": "x", "quality_gate": {"max_critical": -1}}))
    assert_error("quality_gate.max_critical must be a non-negative integer", validate_config({"project_path": "x", "quality_gate": {"max_critical": "notint"}}))
    assert_error("quality_gate.min_fleet_score must be a non-negative number", validate_config({"project_path": "x", "quality_gate": {"min_fleet_score": -1.5}}))
    assert_error("quality_gate.min_cvss_threshold must be a non-negative number", validate_config({"project_path": "x", "quality_gate": {"min_cvss_threshold": "notnum"}}))
    
    # scanner_configs check
    assert_error("scanner_configs must be a dictionary", validate_config({"project_path": "x", "scanner_configs": []}))

@pytest.mark.asyncio
async def test_validation_fails(tmp_path):
    sm = SettingsManager()
    proj = await sm.register_project("test-project", str(tmp_path))
    with pytest.raises(ConfigurationError) as e:
        await load_full_config(sm, proj.id, global_overrides={"fail_on_severity": "INVALID"})
    assert "fail_on_severity must be one of" in str(e.value)
    await sm.delete_project(proj.id)

@pytest.mark.asyncio
async def test_missing_yaml(tmp_path):
    sm = SettingsManager()
    proj = await sm.register_project("test-project", str(tmp_path))
    config = await load_full_config(sm, proj.id)
    assert config["project_path"] == str(tmp_path)
    await sm.delete_project(proj.id)
