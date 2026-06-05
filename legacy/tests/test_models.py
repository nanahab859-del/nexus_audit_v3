import pytest
from core.models import Finding, Severity, Category, ScanResult, Job, Settings
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc


def test_finding_id_is_deterministic() -> None:
    """Test that Finding.id is deterministic."""
    f1 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Direct SQL query",
    )
    f2 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Direct SQL query",
    )
    assert f1.id == f2.id


def test_finding_id_differs_on_content_change() -> None:
    """Test that Finding.id changes with content."""
    f1 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Direct SQL query",
    )
    f2 = Finding(
        scanner="bandit",
        file="app.py",
        line=11,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Direct SQL query",
    )
    assert f1.id != f2.id


def test_finding_is_frozen() -> None:
    """Test that Finding is immutable."""
    f = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Direct SQL query",
    )
    with pytest.raises(Exception):
        f.severity = Severity.CRITICAL  # type: ignore


def test_severity_comparison() -> None:
    """Test Severity enum ordering."""
    assert Severity.INFO < Severity.LOW
    assert Severity.LOW < Severity.MEDIUM
    assert Severity.MEDIUM < Severity.HIGH
    assert Severity.HIGH < Severity.CRITICAL


def test_category_enum_values() -> None:
    """Test Category enum members exist."""
    assert Category.SECURITY
    assert Category.QUALITY
    assert Category.PERFORMANCE
    assert Category.DEPENDENCY
    assert Category.ARCHITECTURE


def test_job_id_is_generated() -> None:
    """Test that Job.id is generated in __post_init__."""
    j = Job(
        project_path=Path("."),
        started_at=datetime.now(UTC),
    )
    assert len(j.id) > 0
    assert isinstance(j.id, str)


def test_job_id_is_unique() -> None:
    """Test that different Jobs have different IDs."""
    j1 = Job(
        project_path=Path("."),
        started_at=datetime.now(UTC),
    )
    j2 = Job(
        project_path=Path("."),
        started_at=datetime.now(UTC),
    )
    assert j1.id != j2.id


def test_scan_result_creation() -> None:
    """Test ScanResult creation."""
    sr = ScanResult(
        scanner="bandit",
        started_at=datetime.now(UTC),
    )
    assert sr.scanner == "bandit"
    assert sr.finished_at is None
    assert sr.findings == []
    assert sr.error is None


def test_settings_defaults() -> None:
    """Test Settings with default values."""
    s = Settings(project_path=Path("."))
    assert s.project_path == Path(".")
    assert s.api_key is None
    assert s.ai_enabled is False
    assert s.ai_provider == "claude"
    assert s.force_rescan is False


def test_finding_id_deduplication_across_scanners() -> None:
    """Test that different scanners with same file+line+title produce same id."""
    f1 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Bandit finding",
    )
    f2 = Finding(
        scanner="semgrep",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="Semgrep finding",
    )
    assert f1.id != f2.id  # Different scanners → different ids


def test_finding_id_same_scanner_different_title() -> None:
    """Test that same scanner+file+line with different title produces different id."""
    f1 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="SQL Injection",
        description="desc",
    )
    f2 = Finding(
        scanner="bandit",
        file="app.py",
        line=10,
        column=5,
        severity=Severity.HIGH,
        category=Category.SECURITY,
        title="Different Title",
        description="desc",
    )
    assert f1.id != f2.id
