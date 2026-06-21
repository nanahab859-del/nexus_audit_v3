import pytest
import json
from core.primitives.models import Severity
from plugins.architecture.lizard_plugin import LizardScanner
from plugins.dependency.license_plugin import LicenseAuditScanner
from plugins.dependency.safety_plugin import PipAuditScanner
from plugins.generic_script_scanner import GenericScriptScanner
from plugins.security.django_settings_plugin import DjangoSettingsScanner
from plugins.security.secretscrub_plugin import SecretScrubScanner
from plugins.security.bandit_plugin import BanditScanner
from unittest.mock import patch, AsyncMock

class DummyBus:
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass

def test_lizard_parsing_invalid():
    scanner = LizardScanner({}, DummyBus())
    # Should skip invalid lines and handle exceptions without dying
    output = "invalid,line,format\n1,2,3\n100,2,3,4,5,6,app.py,long_func,long_func,10,100\n"
    findings = scanner._parse_output(output)
    # the second line is too short, third line is valid but no complexity threshold breach unless config says so?
    # wait, LizardScanner uses config["complexity_threshold"], default 15
    assert len(findings) == 1

def test_license_audit_parsing_clean():
    scanner = LicenseAuditScanner({}, DummyBus())
    scanner.config = {"flagged_licenses": ["GPL"]}
    output = json.dumps([{"Name": "MITPackage", "Version": "1.0", "License": "MIT"}])
    findings = scanner._parse_output(output)
    assert len(findings) == 0

def test_safety_parsing_no_vulns():
    scanner = PipAuditScanner({}, DummyBus())
    output = json.dumps({"dependencies": [{"name": "django", "version": "2.0", "vulns": []}]})
    findings = scanner._parse_output(output)
    assert len(findings) == 0

def test_generic_script_parsing_regex():
    scanner = GenericScriptScanner({}, DummyBus())
    scanner.config = {
        "output_format": "regex",
        "parse_pattern": r"(?P<severity>[A-Z]+):(?P<file>.+):(?P<line>\d+):(?P<message>.+)"
    }
    output = "HIGH:app.py:10:something broken\nUNKNOWN:app.py:11:other issue\n"
    findings = scanner._parse_output(output, scanner.config)
    assert len(findings) == 2
    assert findings[0].severity == Severity.HIGH
    assert findings[1].severity == Severity.MEDIUM

@pytest.mark.asyncio
async def test_django_settings_scan_no_issues(tmp_path):
    scanner = DjangoSettingsScanner({}, DummyBus())
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("DEBUG=False\nSECRET_KEY='good_long_key_for_production'\nALLOWED_HOSTS=['localhost']\nSECURE_HSTS_SECONDS=31536000\nSECURE_SSL_REDIRECT=True\nSESSION_COOKIE_SECURE=True\nCSRF_COOKIE_SECURE=True\nSECURE_BROWSER_XSS_FILTER=True\nSECURE_CONTENT_TYPE_NOSNIFF=True\nX_FRAME_OPTIONS='DENY'\n")
    
    findings = await scanner.scan(tmp_path, {}, DummyBus())
    assert len(findings) == 0

@pytest.mark.asyncio
async def test_django_settings_scan_manage_py(tmp_path):
    scanner = DjangoSettingsScanner({}, DummyBus())
    (tmp_path / "manage.py").write_text("")
    subdir = tmp_path / "myproj"
    subdir.mkdir()
    settings_file = subdir / "settings.py"
    settings_file.write_text("DEBUG=False\nSECRET_KEY='good_long_key_for_production'\n")
    
    findings = await scanner.scan(tmp_path, {}, DummyBus())
    assert len(findings) == 0

@pytest.mark.asyncio
async def test_django_settings_scan_missing_file(tmp_path):
    scanner = DjangoSettingsScanner({}, DummyBus())
    findings = await scanner.scan(tmp_path, {}, DummyBus())
    assert len(findings) == 0

@pytest.mark.asyncio
async def test_secretscrub_parsing_more_cases(tmp_path):
    scanner = SecretScrubScanner({}, DummyBus())
    test_file = tmp_path / "test.py"
    test_file.write_text("AKIAIOSFODNN7EXAMPLE\n")
    
    env_file = tmp_path / ".env"
    env_file.write_text("foo=bar")
    
    findings = await scanner.scan(tmp_path, {"exclude_paths": ["*.txt"], "additional_patterns": [r"CUSTOM_SECRET"]}, DummyBus())
    assert len(findings) >= 2
    assert any("aws-access-key" in f.rule_id for f in findings)
    assert any("dangerous-filename" in f.rule_id for f in findings)

def test_secretscrub_entropy():
    score = SecretScrubScanner._entropy_score("AABBCCDD")
    assert score > 0
    assert SecretScrubScanner._entropy_score("") == 0.0

@pytest.mark.asyncio
async def test_bandit_args_and_scan(tmp_path):
    scanner = BanditScanner({}, DummyBus())
    
    # args
    args1 = await scanner._build_args(tmp_path, {"strictness": "high", "exclude_paths": ["venv"], "skip_checks": ["B101"]})
    assert "-lll" in args1
    assert "venv" in args1
    
    args2 = await scanner._build_args(tmp_path, {"strictness": "low"})
    assert "-l" in args2
    
    # parse invalid
    assert scanner._parse_output("{invalid json}") == []
    
    # parse LOW
    output = json.dumps({"results": [{"issue_severity": "LOW"}]})
    assert scanner._parse_output(output)[0].severity == Severity.LOW

    # scan not installed
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        assert await scanner.scan(tmp_path, {}, DummyBus()) == []

    # scan failed exit code
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (2, "", "error")
            assert await scanner.scan(tmp_path, {}, DummyBus()) == []

@pytest.mark.asyncio
async def test_safety_args_and_scan(tmp_path):
    from plugins.dependency.safety_plugin import PipAuditScanner
    scanner = PipAuditScanner({}, DummyBus())
    
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("django==3.0")
    
    args1 = await scanner._build_args(tmp_path, {
        "cache_dir": "/tmp/cache"
    })
    assert "--requirement" in args1
    assert str(req_file) in args1
    assert "--cache-dir" in args1
    assert "/tmp/cache" in args1
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        assert await scanner.scan(tmp_path, {}, DummyBus()) == []

    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "", "error")
            assert await scanner.scan(tmp_path, {}, DummyBus()) == []

@pytest.mark.asyncio
async def test_eslint_args_and_scan(tmp_path):
    from plugins.quality.eslint_plugin import ESLintScanner
    scanner = ESLintScanner({}, DummyBus())
    
    config_file = tmp_path / ".eslintrc"
    config_file.write_text("{}")
    
    args1 = await scanner._build_args(tmp_path, {"exclude_paths": ["node_modules"]})
    assert "--ignore-pattern" in args1
    assert "node_modules" in args1
    
    # Hit missing file path
    assert await scanner.scan(tmp_path / "nonexistent", {}, DummyBus()) == []
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            # Hit exit code > 1
            mock_run.return_value = (2, "", "error")
            assert await scanner.scan(tmp_path, {}, DummyBus()) == []
            
            # Hit invalid JSON
            mock_run.return_value = (0, "{invalid json}", "")
            assert await scanner.scan(tmp_path, {}, DummyBus()) == []

@pytest.mark.asyncio
async def test_semgrep_args_and_scan(tmp_path):
    from plugins.security.semgrep_plugin import SemgrepScanner
    scanner = SemgrepScanner({}, DummyBus())
    
    args1 = await scanner._build_args(tmp_path, {})
    assert "--config" in args1
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        assert await scanner.scan(tmp_path, {}, DummyBus()) == []

    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (2, "", "error")
            assert await scanner.scan(tmp_path, {}, DummyBus()) == []

