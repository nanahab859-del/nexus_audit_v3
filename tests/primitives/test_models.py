import pytest
from core.primitives.models import Finding, Severity, Category, ProjectSettings, RetentionPolicy, QualityGate, PipelineConfig, SuppressionPolicy, finding_to_dict

def test_finding_to_dict_with_all_optional_fields_none():
    f = Finding(
        id="1", fingerprint=None, scanner="s", rule_id="r",
        file="f", line=1, column=0, severity=Severity.LOW,
        category=Category.QUALITY, title="t", description="d",
        cwe=None, cvss_score=None, suggestion=None, snippet=None
    )
    d = finding_to_dict(f)
    assert d["cwe"] is None
    assert d["cvss_score"] is None
    assert d["suggestion"] is None
    assert d["snippet"] is None
    assert d["fingerprint"] is None

def test_severity_ordering():
    assert Severity.CRITICAL.value > Severity.HIGH.value
    assert Severity.HIGH.value > Severity.MEDIUM.value
    assert Severity.MEDIUM.value > Severity.LOW.value
    assert Severity.LOW.value > Severity.INFO.value

def test_project_settings_post_init_validation():
    with pytest.raises(ValueError):
        ProjectSettings(project_path="", project_name="test")

def test_basic_finding():
    f = Finding(
        id="1", fingerprint="abc", scanner="s", rule_id="r",
        file="f", line=1, column=0, severity=Severity.LOW,
        category=Category.QUALITY, title="t", description="d"
    )
    assert f.id == "1"

def test_configuration_error():
    from core.primitives.models import ConfigurationError
    err = ConfigurationError(["a", "b"])
    assert err.errors == ["a", "b"]
    assert str(err) == "a\nb"

def test_create_finding():
    from core.primitives.models import create_finding, Severity, Category
    finding = create_finding(
        scanner="s", rule_id="r", file="f", line=1, column=2,
        severity=Severity.LOW, category=Category.SECURITY,
        title="t", description="d"
    )
    assert finding.scanner == "s"
