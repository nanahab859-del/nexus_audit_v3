#!/usr/bin/env python3
"""Fast verification of critical systems (skips slow DNA builder)."""

import asyncio
import json
from pathlib import Path

from core.models import Finding, Severity, Category, Job
from core.rules_engine import RulesEngine
from core.atomic import write_json
from core.settings import load as load_settings
from orchestrator import _serialize_finding


async def verify():
    print('✅ PHASE A: Imports & Models')
    print('  ✓ All imports successful')
    
    print('\n✅ PHASE B: Rules Engine')
    try:
        rules = RulesEngine(Path('default_rules.yaml'))
        loaded = rules.load()
        errors = rules.validate()
        print(f'  ✓ Loaded {len(loaded)} rules')
        print(f'  ✓ Validation errors: {len(errors)} (expected 0)')
    except Exception as e:
        print(f'  ✗ ERROR: {e}')
        return False
    
    print('\n✅ PHASE C: Finding Serialization')
    try:
        test_finding = Finding(
            scanner='bandit',
            file='core/security.py',
            line=42,
            column=5,
            severity=Severity.HIGH,
            category=Category.SECURITY,
            title='Hardcoded Secret Found',
            description='Potential hardcoded secret in code',
            suggestion='Use environment variables'
        )
        
        serialized = _serialize_finding(test_finding)
        json_str = json.dumps(serialized)
        
        assert isinstance(serialized['severity'], str), f"Expected str, got {type(serialized['severity'])}"
        assert isinstance(serialized['category'], str), f"Expected str, got {type(serialized['category'])}"
        assert serialized['severity'] == 'HIGH', f"Expected 'HIGH', got {serialized['severity']}"
        
        print(f'  ✓ Finding serialized: {len(json_str)} bytes')
        print(f'  ✓ Severity: {serialized["severity"]} (string)')
        print(f'  ✓ Category: {serialized["category"]} (string)')
    except Exception as e:
        print(f'  ✗ ERROR: {e}')
        return False
    
    print('\n✅ PHASE D: Settings Loading')
    try:
        settings = load_settings('settings.json')
        print(f'  ✓ Settings loaded')
        print(f'  ✓ Project path: {settings.project_path}')
    except Exception as e:
        print(f'  ✗ ERROR: {e}')
        return False
    
    print('\n✅ PHASE E: Job Model')
    try:
        job = Job(
            job_id='test-123',
            project_path=Path('/test'),
            status='running'
        )
        job.status = 'completed'
        print(f'  ✓ Job model instantiated')
        print(f'  ✓ Job status: {job.status}')
    except Exception as e:
        print(f'  ✗ ERROR: {e}')
        return False
    
    print('\n✅ PHASE F: Atomic JSON Write')
    try:
        test_data = {
            'test': 'data',
            'findings': [serialized],
            'timestamp': '2026-06-02T00:00:00',
            'metadata': {
                'scanner': 'test-suite',
                'version': '1.0.0'
            }
        }
        test_path = Path('_test_output_verify.json')
        
        # Write
        await write_json(test_path, test_data)
        assert test_path.exists(), "JSON file not created"
        
        # Read back
        with open(test_path) as f:
            loaded_data = json.load(f)
        
        assert loaded_data['findings'][0]['severity'] == 'HIGH'
        assert len(loaded_data['findings']) == 1
        
        size = test_path.stat().st_size
        test_path.unlink()
        
        print(f'  ✓ JSON written: {size} bytes')
        print(f'  ✓ JSON read back: {len(loaded_data["findings"])} findings')
        print(f'  ✓ Round-trip successful')
    except Exception as e:
        print(f'  ✗ ERROR: {e}')
        return False
    
    print('\n' + '='*50)
    print('✅ ✅ ✅  ALL CRITICAL SYSTEMS OPERATIONAL ✅ ✅ ✅')
    print('='*50)
    print('\nThe pipeline is ready for end-to-end testing!')
    return True


if __name__ == '__main__':
    try:
        success = asyncio.run(verify())
        exit(0 if success else 1)
    except Exception as e:
        print(f'\n❌ CRITICAL ERROR: {e}')
        import traceback
        traceback.print_exc()
        exit(1)
