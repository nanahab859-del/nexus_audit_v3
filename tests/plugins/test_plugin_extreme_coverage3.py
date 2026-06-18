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
async def test_extreme_mypy(tmp_path):
    from plugins.quality.mypy_plugin import MypyScanner
    bus = DummyBus()
    scanner = MypyScanner({}, bus)
    
    args = await scanner._build_args(tmp_path, {"exclude_paths": ["venv"], "strict": True})
    assert "--exclude" in args
    assert "--strict" in args
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock, return_value=True), \
         patch.object(scanner, '_run_tool', new_callable=AsyncMock, return_value=(2, "", "error")):
        assert await scanner.scan(tmp_path, {}, bus) == []

@pytest.mark.asyncio
async def test_extreme_vulture(tmp_path):
    from plugins.quality.vulture_plugin import VultureScanner
    bus = DummyBus()
    scanner = VultureScanner({}, bus)
    
    args = await scanner._build_args(tmp_path, {"min_confidence": 70})
    assert "--min-confidence" in args
    assert "70" in args
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock, return_value=True), \
         patch.object(scanner, '_run_tool', new_callable=AsyncMock, return_value=(2, "", "error")):
        assert await scanner.scan(tmp_path, {}, bus) == []

@pytest.mark.asyncio
async def test_extreme_lizard(tmp_path):
    from plugins.architecture.lizard_plugin import LizardScanner
    bus = DummyBus()
    scanner = LizardScanner({}, bus)
    
    assert scanner._parse_output("") == []
    
    csv_output = "NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end\n31,1,10,2,31,0,test.py,test_low,test_low,1,31\n"
    findings = scanner._parse_output(csv_output)
    assert len(findings) == 1
    assert findings[0].severity.name == "LOW"
    
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock, return_value=False):
        assert await scanner.scan(tmp_path, {}, bus) == []
        assert await scanner.scan(tmp_path, {}, bus) == []

@pytest.mark.asyncio
async def test_extreme_eslint(tmp_path):
    from plugins.quality.eslint_plugin import ESLintScanner
    bus = DummyBus()
    scanner = ESLintScanner({}, bus)
    
    # Force FileNotFoundError
    with patch.object(scanner, '_check_tool', new_callable=AsyncMock, return_value=True):
        assert await scanner.scan(tmp_path / "never_exists", {}, bus) == []
