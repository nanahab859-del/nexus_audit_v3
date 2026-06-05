import pytest
from core.models import Finding, Severity, Category, Persistence, FixStatus, finding_to_dict

def test_finding_to_dict():
    f = Finding(
        id="1234567890abcdef",
        scanner="bandit",
        file="auth.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="Test Finding",
        description="A description"
    )
    
    data = finding_to_dict(f)
    
    assert data["id"] == "1234567890abcdef"
    assert data["severity"] == "HIGH"
    assert data["category"] == "security"
    assert data["persistence"] == "new"
    assert data["fix_status"] == "open"
    assert data["suggestion"] is None
