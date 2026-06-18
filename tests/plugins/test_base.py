import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
from typing import List, Any

from plugins.base import BaseScanner
from core.primitives.models import Finding, Category
from core.primitives.events import EventBus
from core.infra.tool_resolver import ToolNotFoundError

class DummyScanner(BaseScanner):
    name = "dummy"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY
    requires_tool = True
    tool_name = "dummy_tool"
    ecosystem = "python"
    
    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        return []
        
    def _parse_output(self, output: Any) -> List[Finding]:
        return []

class DummyScannerNoTool(DummyScanner):
    requires_tool = False

class DummyBus:
    async def publish_log(self, *args, **kwargs):
        pass

@pytest.fixture
def dummy_bus():
    return DummyBus()

@pytest.mark.asyncio
async def test_run_tool_success(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        
        mock_resolve.return_value = ["/path/to/dummy_tool"]
        
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        async def mock_communicate():
            return (b"output", b"")
        mock_proc.communicate = mock_communicate
        
        mock_exec.return_value = mock_proc
        
        code, stdout, stderr = await scanner._run_tool(["--arg"], dummy_bus)
        
        assert code == 0
        assert stdout == "output"
        assert stderr == ""

@pytest.mark.asyncio
async def test_run_tool_timeout(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("asyncio.wait_for") as mock_wait_for:
        
        mock_resolve.return_value = ["/path/to/dummy_tool"]
        
        mock_proc = MagicMock()
        mock_exec.return_value = mock_proc
        
        # Simulate timeout
        mock_wait_for.side_effect = asyncio.TimeoutError()
        
        code, stdout, stderr = await scanner._run_tool(["--arg"], dummy_bus)
        
        assert code == 1
        assert stdout == ""
        assert stderr == "Timeout exceeded"
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()

@pytest.mark.asyncio
async def test_run_tool_file_not_found(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = ToolNotFoundError()
        
        code, stdout, stderr = await scanner._run_tool(["--arg"], dummy_bus)
        
        assert code == 127
        assert stdout == ""
        assert stderr == "Tool not found"

@pytest.mark.asyncio
async def test_run_tool_exception(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = Exception("Unknown error")
        
        code, stdout, stderr = await scanner._run_tool(["--arg"], dummy_bus)
        
        assert code == 1
        assert stdout == ""
        assert stderr == "Unknown error"

@pytest.mark.asyncio
async def test_check_tool_available(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = ["/path/to/dummy_tool"]
        
        is_available = await scanner._check_tool(dummy_bus)
        assert is_available is True

@pytest.mark.asyncio
async def test_check_tool_not_available(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch.object(dummy_bus, "publish_log", new_callable=AsyncMock) as mock_publish:
        mock_resolve.side_effect = ToolNotFoundError()
        
        is_available = await scanner._check_tool(dummy_bus)
        assert is_available is False
        mock_publish.assert_called_once_with("warning", "Scanner 'dummy' requires tool 'dummy_tool' in python")

@pytest.mark.asyncio
async def test_check_tool_builtin(dummy_bus):
    scanner = DummyScannerNoTool({}, dummy_bus)
    with patch("core.infra.tool_resolver.ToolResolver.resolve", new_callable=AsyncMock) as mock_resolve:
        is_available = await scanner._check_tool(dummy_bus)
        assert is_available is True
        mock_resolve.assert_not_called()

@pytest.mark.asyncio
async def test_build_args_default(dummy_bus):
    scanner = DummyScanner({}, dummy_bus)
    args = await scanner._build_args(Path("."), {})
    assert args == []

def test_validate_scanner_class():
    from plugins.base import validate_scanner_class
    
    class InvalidScanner:
        pass
    
    errors = validate_scanner_class(InvalidScanner)
    assert len(errors) > 0
    assert any("Missing required attribute: name" in e for e in errors)
    assert any("scan() method must be implemented" in e for e in errors)
    assert any("_parse_output() method must be implemented" in e for e in errors)
    
    class InvalidScanner2:
        name = "test"
        version = "1"
        languages = "python"  # should be list
        category = "security" # should be enum
        tool_name = "test"
        requires_tool = False
        def scan(self): pass
        def _parse_output(self): pass

    errors2 = validate_scanner_class(InvalidScanner2)
    assert len(errors2) > 0
    assert any("languages must be a list" in e for e in errors2)
    assert any("category must be a Category enum" in e for e in errors2)

def test_base_abstract_methods():
    from plugins.base import BaseScanner
    assert BaseScanner.scan.__isabstractmethod__ == True
    assert BaseScanner._parse_output.__isabstractmethod__ == True
