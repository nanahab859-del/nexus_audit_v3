#!/usr/bin/env python3
"""Test critical path: Finding creation, serialization, JSON conversion."""

from core.models import Finding, Severity, Category
from orchestrator import _serialize_finding
import json

# Create test finding
f = Finding(
    scanner='bandit',
    file='core/security.py',
    line=42,
    column=5,
    severity=Severity.HIGH,
    category=Category.SECURITY,
    title='Hardcoded Secret',
    description='Potential hardcoded secret',
    suggestion='Use environment variables'
)

# Serialize
s = _serialize_finding(f)
json_str = json.dumps(s)

print(f'✓ Finding created: {f.id}')
print(f'✓ Serialized: {len(json_str)} bytes')
print(f'✓ Severity: {s["severity"]} (type: {type(s["severity"]).__name__})')
print(f'✓ Category: {s["category"]} (type: {type(s["category"]).__name__})')
print(f'\n✅ CRITICAL PIPELINE VERIFIED')
