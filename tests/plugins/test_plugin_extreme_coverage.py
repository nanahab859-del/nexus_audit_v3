import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from core.primitives.events import EventBus

class DummyBus(EventBus):
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass
    async def publish_finding(self, *args, **kwargs): pass
    async def start(self): pass
    async def stop(self): pass

@pytest.mark.asyncio
async def test_extreme_parsing_coverage(tmp_path):
    from plugins.quality.pylint_plugin import PylintScanner
    from plugins.quality.ruff_plugin import RuffScanner
    from plugins.quality.djlint_plugin import DjLintScanner
    from plugins.quality.eslint_plugin import ESLintScanner
    from plugins.quality.mypy_plugin import MypyScanner
    from plugins.quality.vulture_plugin import VultureScanner
    from plugins.architecture.lizard_plugin import LizardScanner
    from plugins.dependency.license_plugin import LicenseAuditScanner
    from plugins.security.trufflehog_plugin import TruffleHogScanner
    
    bus = DummyBus()
    
    scanners = [
        PylintScanner({}, bus),
        RuffScanner({}, bus),
        DjLintScanner({}, bus),
        ESLintScanner({}, bus),
        LicenseAuditScanner({}, bus),
        TruffleHogScanner({}, bus),
    ]
    
    for scanner in scanners:
        # Hit `if not output: return []`
        assert scanner._parse_output("") == []
        
        # Hit `except json.JSONDecodeError: return []`
        assert scanner._parse_output("{invalid json}") == []

@pytest.mark.asyncio
async def test_extreme_args_coverage(tmp_path):
    from plugins.quality.pylint_plugin import PylintScanner
    from plugins.quality.ruff_plugin import RuffScanner
    
    bus = DummyBus()
    
    pylint = PylintScanner({}, bus)
    args = await pylint._build_args(tmp_path, {"enable": ["C0111"]})
    assert "--enable" in args
    
    ruff = RuffScanner({}, bus)
    args = await ruff._build_args(tmp_path, {"ignore": ["E501"]})
    assert "--ignore" in args

@pytest.mark.asyncio
async def test_extreme_scan_errors(tmp_path):
    from plugins.quality.pylint_plugin import PylintScanner
    from plugins.quality.ruff_plugin import RuffScanner
    from plugins.architecture.lizard_plugin import LizardScanner
    from plugins.dependency.license_plugin import LicenseAuditScanner
    
    bus = DummyBus()
    
    pylint = PylintScanner({}, bus)
    with patch.object(pylint, '_check_tool', new_callable=AsyncMock, return_value=True), \
         patch.object(pylint, '_run_tool', new_callable=AsyncMock, return_value=(32, "", "usage error")):
        assert await pylint.scan(tmp_path, {}, bus) == []

    ruff = RuffScanner({}, bus)
    with patch.object(ruff, '_check_tool', new_callable=AsyncMock, return_value=True), \
         patch.object(ruff, '_run_tool', new_callable=AsyncMock, return_value=(2, "", "error")):
        assert await ruff.scan(tmp_path, {}, bus) == []

    lizard = LizardScanner({}, bus)
    with patch.object(lizard, '_check_tool', new_callable=AsyncMock, return_value=True), \
         patch.object(lizard, '_run_tool', new_callable=AsyncMock, return_value=(2, "", "error")):
        assert await lizard.scan(tmp_path, {}, bus) == []

