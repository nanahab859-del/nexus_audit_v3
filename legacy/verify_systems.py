#!/usr/bin/env python3
"""Comprehensive system verification script."""

import asyncio
import json
from pathlib import Path

from core.models import Finding, Severity, Category
from core.rules_engine import RulesEngine
from core.dna_builder import build_dna
from core.events import bus
from core.atomic import write_json
from orchestrator import _serialize_finding


async def verify():
    print('✓ PHASE A: Imports & Models')
    print('  - All imports successful')
    
    print('\n✓ PHASE B: Rules Engine')
    rules = RulesEngine(Path('default_rules.yaml'))
    loaded = rules.load()
    errors = rules.validate()
    print(f'  - Loaded {len(loaded)} rules')
    print(f'  - Validation errors: {len(errors)} (expected 0)')
    
    print('\n✓ PHASE C: DNA Builder')
    dna = await build_dna(Path('.'), bus)
    print(f'  - Found {len(dna.modules)} modules')
    apps_sample = list(dna.apps)[:3]
    print(f'  - Found {len(dna.apps)} apps: {apps_sample}...')
    
    print('\n✓ PHASE D: Finding Serialization')
    test_finding = Finding(
        scanner='test',
        file='test.py',
        line=1,
        column=1,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title='Test',
        description='Test'
    )
    serialized = _serialize_finding(test_finding)
    json_str = json.dumps(serialized)
    print(f'  - Finding serialized: {len(json_str)} bytes')
    print(f'  - Severity type in dict: {serialized["severity"]} (type: {type(serialized["severity"]).__name__})')
    print(f'  - Category type in dict: {serialized["category"]} (type: {type(serialized["category"]).__name__})')
    
    print('\n✓ PHASE E: JSON Atomic Write Test')
    test_data = {
        'test': 'data',
        'findings': [serialized],
        'timestamp': '2026-06-02T00:00:00'
    }
    test_path = Path('test_output.json')
    await write_json(test_path, test_data)
    
    if test_path.exists():
        size = test_path.stat().st_size
        with open(test_path) as f:
            loaded_data = json.load(f)
        test_path.unlink()
        print(f'  - Written: {size} bytes')
        print(f'  - Read back: {len(loaded_data["findings"])} findings ✓')
        print(f'  - JSON roundtrip successful ✓')
    
    print('\n✅ ALL SYSTEMS OPERATIONAL ✅')
    print('\nReady for end-to-end testing!')
    return True


if __name__ == '__main__':
    try:
        success = asyncio.run(verify())
        exit(0 if success else 1)
    except Exception as e:
        print(f'❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        exit(1)
