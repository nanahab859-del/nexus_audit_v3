import pytest
from core.primitives.models import Severity, Category, Finding
from plugins.security.bandit_plugin import BanditScanner
from plugins.quality.vulture_plugin import VultureScanner
from plugins.security.semgrep_plugin import SemgrepScanner
from plugins.dependency.safety_plugin import PipAuditScanner
from plugins.quality.radon_plugin import RadonScanner
from plugins.architecture.lizard_plugin import LizardScanner
from plugins.security.django_settings_plugin import DjangoSettingsScanner
from plugins.security.secretscrub_plugin import SecretScrubScanner
from plugins.quality.pylint_plugin import PylintScanner
from plugins.quality.ruff_plugin import RuffScanner
from plugins.quality.mypy_plugin import MypyScanner
from plugins.security.trufflehog_plugin import TruffleHogScanner
from plugins.quality.djlint_plugin import DjLintScanner
from plugins.quality.eslint_plugin import ESLintScanner
from plugins.dependency.license_plugin import LicenseAuditScanner
from plugins.generic_script_scanner import GenericScriptScanner
import json
from pathlib import Path

class DummyBus:
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass
def test_bandit_parsing():
    scanner = BanditScanner({}, DummyBus())
    output = json.dumps({"results": [{"filename": "app.py", "line_number": 10, "issue_text": "hardcoded password", "issue_severity": "HIGH", "issue_confidence": "HIGH", "test_id": "B105", "more_info": "docs"}]})
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].scanner == "bandit"
    assert findings[0].rule_id == "B105"

def test_vulture_parsing():
    scanner = VultureScanner({}, DummyBus())
    output = "app.py:10: unused variable 'x' (60% confidence)"
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert findings[0].category == Category.QUALITY
    assert findings[0].file == "app.py"
    assert findings[0].line == 10

def test_semgrep_parsing():
    scanner = SemgrepScanner({}, DummyBus())
    output = json.dumps({"results": [{"check_id": "python.lang.security", "path": "app.py", "start": {"line": 5, "col": 1}, "extra": {"severity": "ERROR", "message": "dangerous function", "fix": "replace with safe alternative"}}]})
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].rule_id == "python.lang.security"

def test_pip_audit_parsing():
    scanner = PipAuditScanner({}, DummyBus())
    output = json.dumps({"dependencies": [{"name": "django", "version": "2.0", "vulns": [{"id": "CVE-123", "description": "vulnerability found", "fix_versions": ["2.1"]}]}]})
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "django" in findings[0].title

def test_radon_parsing():
    scanner = RadonScanner({}, DummyBus())
    output = json.dumps({"app.py": [{"name": "complex_func", "lineno": 20, "col_offset": 0, "complexity": 15, "rank": "E"}]})
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].file == "app.py"

def test_lizard_parsing():
    scanner = LizardScanner({}, DummyBus())
    output = "120,2,3,4,5,6,app.py,long_func,long_func,10,120\n"
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].file == "app.py"

@pytest.mark.asyncio
async def test_django_settings_scan(tmp_path):
    scanner = DjangoSettingsScanner({}, DummyBus())
    assert scanner._parse_output("") == []
    
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("DEBUG=True\nSECRET_KEY='hunter2'")
    
    class DummyConfig:
        def __init__(self):
            self.settings_file = str(settings_file.absolute())
    scanner.config = DummyConfig()
    
    findings = await scanner.scan(tmp_path, {}, DummyBus())
    assert len(findings) > 0
    assert any("DEBUG" in f.title for f in findings)
    assert any("SECRET_KEY" in f.title for f in findings)

@pytest.mark.asyncio
async def test_secretscrub_scan(tmp_path):
    scanner = SecretScrubScanner({}, DummyBus())
    assert scanner._parse_output("") == []
    
    test_file = tmp_path / "test.py"
    test_file.write_text("password = 'hunter212'")
    
    findings = await scanner.scan(tmp_path, {}, DummyBus())
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH

def test_pylint_parsing():
    scanner = PylintScanner({}, DummyBus())
    output = json.dumps([{"path": "app.py", "line": 10, "column": 0, "message": "Missing docstring", "message-id": "C0116", "type": "convention"}])
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert findings[0].rule_id == "C0116"

def test_ruff_parsing():
    scanner = RuffScanner({}, DummyBus())
    output = json.dumps([{"filename": "app.py", "location": {"row": 10, "column": 1}, "code": "F401", "message": "unused import"}])
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].rule_id == "F401"

def test_mypy_parsing():
    scanner = MypyScanner({}, DummyBus())
    output = "app.py:10: error: Argument 1 has incompatible type [arg-type]"
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].file == "app.py"
    assert findings[0].line == 10

def test_trufflehog_parsing():
    scanner = TruffleHogScanner({}, DummyBus())
    output = '{"DetectorName": "GitHub", "Raw": "ghp_test123456789", "SourceMetadata": {"Data": {"Filesystem": {"file": "app.py", "line": 1}}}}\n'
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "GitHub" in findings[0].title

def test_djlint_parsing():
    scanner = DjLintScanner({}, DummyBus())
    output = json.dumps([{"file": "index.html", "line": 5, "message": "Unclosed tag", "rule": "T001"}])
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].file == "index.html"

def test_eslint_parsing():
    scanner = ESLintScanner({}, DummyBus())
    output = json.dumps([{"filePath": "app.js", "messages": [{"ruleId": "no-var", "severity": 2, "line": 1, "column": 1, "message": "Unexpected var"}]}])
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].rule_id == "no-var"

def test_license_audit_parsing():
    scanner = LicenseAuditScanner({}, DummyBus())
    class DummyConfig:
        def __init__(self):
            self.flagged_licenses = ["GPL"]
    scanner.config = DummyConfig()
    output = json.dumps([{"Name": "GPLPackage", "Version": "1.0", "License": "GPL"}])
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "GPLPackage" in findings[0].title

def test_generic_script_parsing():
    scanner = GenericScriptScanner({}, DummyBus())
    class DummyConfig:
        def __init__(self):
            self.output_format = "line"
    scanner.config = DummyConfig()
    output = "HIGH:app.py:10:something broken"
    findings = scanner._parse_output(output)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].file == "app.py"
    assert findings[0].line == 10
