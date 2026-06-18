#!/usr/bin/env python3
import sys
import os
import asyncio
from pathlib import Path
import dataclasses
import uuid

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

errors = []
passed = []

async def main():
    print("=" * 60)
    print("Running Layer 1 Primitives Verification...")
    
    # --- settings.py verification ---
    from core.primitives.settings import SettingsManager
    from core.primitives.models import Severity
    
    sm = SettingsManager()
    
    # Test project registration
    test_proj_name = f"verify_proj_{uuid.uuid4().hex[:6]}"
    proj_path = Path("/tmp") / test_proj_name
    proj_path.mkdir(parents=True, exist_ok=True)
    
    project = await sm.register_project(test_proj_name, str(proj_path))
    passed.append(f"Registered project {test_proj_name} (ID: {project.id})")
    
    # Reload settings manager to test deserialization from disk
    sm = SettingsManager()
    ws = await sm.load_workspace()
    
    if project.id in ws.projects:
        passed.append("Project appears correctly in workspace after load")
    else:
        errors.append("Project missing from workspace after load")
        
    p = ws.projects[project.id]
    if isinstance(p.settings.quality_gate.max_critical, int):
        passed.append("quality_gate.max_critical returns an int, not dict/AttributeError")
    else:
        errors.append(f"quality_gate.max_critical has wrong type: {type(p.settings.quality_gate.max_critical)}")
        
    # Patch settings
    await sm.patch_project_settings(project.id, {"quality_gate": {"min_fleet_score": 75.5}})
    
    # Reload settings manager again
    sm = SettingsManager()
    p = await sm.load_project(project.id)
    if p.settings.quality_gate.min_fleet_score == 75.5:
        passed.append("config patch applied successfully without crash on next load")
    else:
        errors.append("config patch min_fleet_score check failed")
        
    # Delete project
    await sm.delete_project(project.id)
    try:
        sm.get_project(project.id)
        errors.append("get_project() returned stale data after delete")
    except KeyError:
        passed.append("get_project() raises KeyError after project:delete")
        
    # Test save_workspace does not mutate
    ws1 = await sm.load_workspace()
    ws1.global_settings.api_key = "test-key-123"
    await sm.save_workspace(ws1)
    if ws1.global_settings.api_key == "test-key-123":
        passed.append("save_workspace does not mutate the passed object")
    else:
        errors.append("save_workspace mutated the passed object")
        
    ws_dict_1 = (Path.home() / ".nexus_audit" / "workspace.json").read_text()
    await sm.save_workspace(ws1)
    ws_dict_2 = (Path.home() / ".nexus_audit" / "workspace.json").read_text()
    import json
    d1 = json.loads(ws_dict_1)
    d2 = json.loads(ws_dict_2)
    
    # The API key ciphertext will be different due to Fernet IV/timestamp, so we pop it
    if "global_settings" in d1 and "api_key" in d1["global_settings"]:
        d1["global_settings"].pop("api_key", None)
        d2["global_settings"].pop("api_key", None)
        
    if d1 == d2:
        passed.append("save_workspace called twice produces structurally identical JSON")
    else:
        errors.append("save_workspace called twice produced different JSON structure")
        
    # Test int severity deserialization
    p_data = {"id": "test", "name": "test", "path": "/tmp", "settings": {"fail_on_severity": 4, "project_path": "/tmp"}}
    try:
        p_obj = sm._deserialise_project(p_data)
        if p_obj.settings.fail_on_severity == Severity.CRITICAL:
            passed.append("Project with fail_on_severity: 4 loads as Severity.CRITICAL")
        else:
            errors.append("Project with fail_on_severity: 4 did not load correctly")
    except Exception as e:
        errors.append(f"Failed to deserialise int severity: {e}")
        
    # --- security.py verification ---
    from core.primitives.security import encrypt, decrypt
    if not hasattr(sys.modules['core.primitives.security'], 'derive_key'):
        passed.append("derive_key export removed from security.py")
    else:
        errors.append("derive_key is still present in security.py")
        
    enc = encrypt("sk-test-key")
    if enc.startswith("gAAAAA"):
        passed.append("encrypt() returns string starting with gAAAAA")
    else:
        errors.append("encrypt() output does not start with gAAAAA")
        
    if decrypt(enc) == "sk-test-key":
        passed.append("decrypt(encrypt()) round trip successful")
    else:
        errors.append("decrypt(encrypt()) failed")
        
    if decrypt("plain-text-value") == "plain-text-value":
        passed.append("decrypt('plain-text-value') returns cleartext (legacy path)")
    else:
        errors.append("decrypt() legacy cleartext path failed")
        
    # Test key rotation / auto-generation
    import core.primitives.security as sec
    if sec._CACHE_PATH.exists():
        sec._CACHE_PATH.unlink()
    sec._FERNET = None
    
    enc2 = encrypt("sk-test-key2")
    if sec._CACHE_PATH.exists():
        passed.append("New key generated automatically when cache deleted")
    else:
        errors.append("New key was not generated")
        
    # --- models.py verification ---
    from core.primitives.models import Finding, Severity, Category, Persistence, FixStatus, to_dict
    f = Finding(
        id=str(uuid.uuid4()), rule_id="1", scanner="s", file="f", line=1, column=0,
        severity=Severity.CRITICAL, category=Category.SECURITY, title="t", description="d"
    )
    if to_dict(f)["severity"] == "CRITICAL":
        passed.append("to_dict(finding)['severity'] returns 'CRITICAL' (name), not 4")
    else:
        errors.append("to_dict() Enum serialization failed")
        
    try:
        from core.infra.config_loader import ConfigurationError
        passed.append("from core.infra.config_loader import ConfigurationError works")
    except ImportError:
        errors.append("Failed to import ConfigurationError from config_loader")
        
    # Summary
    print("\n" + "=" * 60)
    print(f"PASSED ({len(passed)}):")
    for p in passed:
        print(f"  ✓ {p}")

    if errors:
        print(f"\nFAILED ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"\nAll {len(passed)} checks passed — primitives refactor verified.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
