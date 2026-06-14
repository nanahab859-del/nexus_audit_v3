import pytest
import shutil
import asyncio
from pathlib import Path
from core.infra.registry import PluginRegistry
from core.primitives.events import EventBus

# A dummy scanner for testing
dummy_scanner_code = """
from plugins.base import BaseScanner
from core.primitives.models import Category
from typing import ClassVar, List, Any
from pathlib import Path

class DummyScanner(BaseScanner):
    name = "dummy"
    version = "1.0"
    languages = ["python"]
    category = Category.SECURITY
    tool_name = "dummy_tool"
    requires_tool = False
    
    def __init__(self, config: dict, bus: Any):
        self.config = config
        self.bus = bus
    
    def _parse_output(self, output: str):
        return []
        
    async def scan(self, target: Path, config: dict, bus: Any):
        return []
"""

@pytest.mark.asyncio
async def test_load_discovers_scanners(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    # Write a valid scanner
    (plugin_dir / "dummy_plugin.py").write_text(dummy_scanner_code)
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    
    assert "dummy" in registry.names()
    assert len(registry.all()) == 1
    
    # Test get
    cls = registry.get("dummy")
    assert cls is not None
    assert getattr(cls, 'name') == "dummy"
    
    # Test load again (early return)
    registry.load() # should do nothing
    assert len(registry.all()) == 1
    
    # Test reload
    registry.reload()
    assert len(registry.all()) == 1

@pytest.mark.asyncio
async def test_internal_skipped(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    internal_scanner_code = dummy_scanner_code.replace('class DummyScanner(BaseScanner):', 'class InternalScanner(BaseScanner):\n    is_internal = True\n    name = "internal"')
    (plugin_dir / "internal_plugin.py").write_text(internal_scanner_code)
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    
    assert "internal" not in registry.names()

@pytest.mark.asyncio
async def test_duplicate_name_skipped(tmp_path, caplog):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    (plugin_dir / "p1.py").write_text(dummy_scanner_code)
    (plugin_dir / "p2.py").write_text(dummy_scanner_code)
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    
    assert len(registry.all()) == 1
    assert "Duplicate scanner name found: dummy" in caplog.text

@pytest.mark.asyncio
async def test_syntax_error_skipped(tmp_path, caplog):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    (plugin_dir / "bad.py").write_text("this is invalid python syntax")
    
    bus = EventBus()
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load(bus=bus)
    
    assert len(registry.all()) == 0
    # allow async logs to process
    await asyncio.sleep(0.1)

@pytest.mark.asyncio
async def test_missing_plugins_dir(caplog):
    registry = PluginRegistry(plugins_dir=Path("/non/existent/path"))
    registry.load()
    
    assert "Plugins directory not found" in caplog.text

@pytest.mark.asyncio
async def test_instantiate(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    (plugin_dir / "dummy_plugin.py").write_text(dummy_scanner_code)
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    
    bus = EventBus()
    instance = registry.instantiate("dummy", {}, bus)
    assert instance.name == "dummy"
    
    with pytest.raises(KeyError):
        registry.instantiate("non_existent", {}, bus)

@pytest.mark.asyncio
async def test_validation_error_logged(tmp_path, caplog):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    
    # Missing name attribute
    invalid_code = dummy_scanner_code.replace('name = "dummy"', '')
    (plugin_dir / "invalid_plugin.py").write_text(invalid_code)
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    assert "Plugin validation failed" in caplog.text

@pytest.mark.asyncio
async def test_skip_init_py(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("invalid syntax again but should be skipped")
    
    registry = PluginRegistry(plugins_dir=plugin_dir)
    registry.load()
    assert len(registry.all()) == 0

def test_registry_load_runtime_error(tmp_path, monkeypatch):
    from core.infra.registry import PluginRegistry
    import asyncio
    
    class MockBus:
        def publish_log(self, *args, **kwargs): pass
        
    def mock_get_running_loop():
        raise RuntimeError("No loop")
    
    monkeypatch.setattr(asyncio, "get_running_loop", mock_get_running_loop)
    
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "bad.py").write_text("1 / 0")
    
    registry = PluginRegistry(plugins_dir)
    registry.load(bus=MockBus()) # Should catch RuntimeError and use logger.warning

def test_registry_load_no_bus(tmp_path):
    from core.infra.registry import PluginRegistry
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "bad.py").write_text("1 / 0")
    
    registry = PluginRegistry(plugins_dir)
    registry.load(bus=None) # Should use logger.warning
