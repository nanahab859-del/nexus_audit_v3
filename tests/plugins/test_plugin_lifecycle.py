import pytest
import asyncio
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.infra.tool_resolver import ToolResolver, ToolNotFoundError
from core.primitives.commands import CommandRegistry, CommandContext
from core.primitives.settings import SettingsManager
from core.primitives.events import EventBus

class DummyContext(CommandContext):
    def __init__(self):
        self.output = []
        self.settings_manager = None
        self.active_project = None
        self.privilege_level = 3
        self.workspace = None
        
    def write(self, msg: str):
        self.output.append(msg)
        
    def write_error(self, msg: str):
        self.output.append(f"ERROR: {msg}")

@pytest.mark.asyncio
async def test_tool_resolver_node_installed():
    resolver = ToolResolver()
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/eslint"
        assert await resolver.is_available("eslint", "node") == True
        result = await resolver.resolve("eslint", "node")
        assert result == ["/usr/bin/eslint"]

@pytest.mark.asyncio
async def test_tool_resolver_node_not_installed():
    resolver = ToolResolver()
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None
        # Also mock Path("node_modules").is_file to False
        with patch("pathlib.Path.is_file") as mock_is_file:
            mock_is_file.return_value = False
            assert await resolver.is_available("eslint", "node") == False
            with pytest.raises(ToolNotFoundError):
                await resolver.resolve("eslint", "node")

@pytest.mark.asyncio
async def test_tool_resolver_binary_installed():
    resolver = ToolResolver()
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/trufflehog"
        assert await resolver.is_available("trufflehog", "binary") == True

@pytest.mark.asyncio
async def test_tool_resolver_binary_not_installed():
    resolver = ToolResolver()
    with patch("shutil.which") as mock_which:
        mock_which.return_value = None
        assert await resolver.is_available("trufflehog", "binary") == False

@pytest.mark.asyncio
async def test_tool_resolver_python_installed_via_venv():
    resolver = ToolResolver()
    with patch("core.infra.tool_resolver.get_venv_python") as mock_get_venv:
        mock_venv = MagicMock()
        mock_get_venv.return_value = mock_venv
        with patch("pathlib.Path.is_file") as mock_is_file, \
             patch("os.access") as mock_access:
            mock_is_file.return_value = True
            mock_access.return_value = True
            assert await resolver.is_available("bandit", "python") == True

@pytest.mark.asyncio
async def test_tool_resolver_python_not_installed():
    resolver = ToolResolver()
    with patch("core.infra.tool_resolver.get_venv_python") as mock_get_venv, \
         patch("shutil.which") as mock_which, \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_get_venv.return_value = None
        mock_which.return_value = None
        
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        async def mock_communicate():
            return (b"", b"")
        mock_proc.communicate = mock_communicate
        mock_exec.return_value = mock_proc
        
        assert await resolver.is_available("bandit", "python") == False

@pytest.mark.asyncio
async def test_scanner_install_python_command():
    registry = CommandRegistry(None)
    ctx = DummyContext()
    await registry._handle_scanner_install(ctx, {"name": "bandit"})
    assert "To install bandit, run: pip install bandit" in ctx.output[0]

@pytest.mark.asyncio
async def test_scanner_install_node_command():
    registry = CommandRegistry(None)
    ctx = DummyContext()
    await registry._handle_scanner_install(ctx, {"name": "eslint"})
    assert "To install eslint, run: npm install -g eslint" in ctx.output[0]

@pytest.mark.asyncio
async def test_scanner_install_binary_command():
    registry = CommandRegistry(None)
    ctx = DummyContext()
    await registry._handle_scanner_install(ctx, {"name": "trufflehog"})
    assert "download the binary" in ctx.output[0].lower()

@pytest.mark.asyncio
async def test_scanner_install_not_found():
    registry = CommandRegistry(None)
    ctx = DummyContext()
    await registry._handle_scanner_install(ctx, {"name": "not_a_real_scanner"})
    assert "ERROR: Scanner not_a_real_scanner not found" in ctx.output[0]
