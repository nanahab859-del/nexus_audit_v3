import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from plugins.security.bandit_plugin import BanditScanner
from plugins.quality.vulture_plugin import VultureScanner
from plugins.security.semgrep_plugin import SemgrepScanner
from plugins.dependency.safety_plugin import PipAuditScanner
from plugins.quality.radon_plugin import RadonScanner
from plugins.architecture.lizard_plugin import LizardScanner
from plugins.quality.pylint_plugin import PylintScanner
from plugins.quality.ruff_plugin import RuffScanner
from plugins.quality.mypy_plugin import MypyScanner
from plugins.security.trufflehog_plugin import TruffleHogScanner
from plugins.quality.djlint_plugin import DjLintScanner
from plugins.quality.eslint_plugin import ESLintScanner
from plugins.dependency.license_plugin import LicenseAuditScanner
from plugins.generic_script_scanner import GenericScriptScanner

class DummyBus:
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass

@pytest.fixture
def dummy_bus():
    return DummyBus()

@pytest.mark.asyncio
@pytest.mark.parametrize("scanner_cls, test_output", [
    (BanditScanner, json.dumps({"results": []})),
    (VultureScanner, ""),
    (SemgrepScanner, json.dumps({"results": []})),
    (PipAuditScanner, json.dumps({"dependencies": []})),
    (RadonScanner, json.dumps({})),
    (LizardScanner, "1,2,3,4,5,6,app.py,long_func,long_func,10,120\n"),
    (PylintScanner, json.dumps([])),
    (RuffScanner, json.dumps([])),
    (MypyScanner, ""),
    (TruffleHogScanner, ""),
    (DjLintScanner, json.dumps([])),
    (ESLintScanner, json.dumps([])),
    (LicenseAuditScanner, json.dumps([])),
    (GenericScriptScanner, ""),
])
async def test_all_scanners_scan(scanner_cls, test_output, dummy_bus, tmp_path):
    scanner = scanner_cls({}, dummy_bus)
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, test_output, "")
            
            # Additional mocks for specific plugins that need files to exist
            if scanner_cls == GenericScriptScanner:
                scanner.config["executable"] = "dummy"
            if scanner_cls == ESLintScanner:
                (tmp_path / ".eslintrc").write_text("{}")
            
            findings = await scanner.scan(tmp_path, scanner.config, dummy_bus)
            
            assert isinstance(findings, list)
            if scanner_cls != GenericScriptScanner:
                mock_check.assert_called_once()
                mock_run.assert_called_once()

@pytest.mark.asyncio
@pytest.mark.parametrize("scanner_cls, test_output", [
    (BanditScanner, json.dumps({"results": []})),
    (VultureScanner, ""),
    (SemgrepScanner, json.dumps({"results": []})),
    (PipAuditScanner, json.dumps({"dependencies": []})),
    (RadonScanner, json.dumps({})),
    (LizardScanner, "1,2,3,4,5,6,app.py,long_func,long_func,10,120\n"),
    (PylintScanner, json.dumps([])),
    (RuffScanner, json.dumps([])),
    (MypyScanner, ""),
    (TruffleHogScanner, ""),
    (DjLintScanner, json.dumps([])),
    (ESLintScanner, json.dumps([])),
    (LicenseAuditScanner, json.dumps([])),
    (GenericScriptScanner, ""),
])
async def test_all_scanners_scan_failure(scanner_cls, test_output, dummy_bus, tmp_path):
    scanner = scanner_cls({}, dummy_bus)
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        with patch.object(scanner, '_run_tool', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, test_output, "error output")
            if scanner_cls == GenericScriptScanner:
                scanner.config["executable"] = "dummy"
            if scanner_cls == ESLintScanner:
                (tmp_path / ".eslintrc").write_text("{}")
            findings = await scanner.scan(tmp_path, scanner.config, dummy_bus)
            assert findings == []
