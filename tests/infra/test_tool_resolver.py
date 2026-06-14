import pytest
import os
import sys
import asyncio
from pathlib import Path
from core.infra.tool_resolver import ToolResolver, ToolNotFoundError

@pytest.mark.asyncio
async def test_venv_bin_found(tmp_path, monkeypatch):
    bin_dir = tmp_path / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    bin_dir.mkdir(parents=True)
    exe = bin_dir / ("dummy.exe" if sys.platform == "win32" else "dummy")
    exe.touch(mode=0o755)
    fake_python = bin_dir / ("python.exe" if sys.platform == "win32" else "python3")
    fake_python.touch(mode=0o755)
    
    monkeypatch.setattr("core.infra.tool_resolver.get_venv_python", lambda: fake_python)
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy")
    assert resolved == [str(exe)]

@pytest.mark.asyncio
async def test_system_path_found():
    resolver = ToolResolver()
    resolved = await resolver.resolve("python3")
    assert resolved is not None
    assert "python3" in resolved[0]

@pytest.mark.asyncio
async def test_module_fallback():
    resolver = ToolResolver()
    resolved = await resolver.resolve("json")
    assert "-m" in resolved
    assert "json" in resolved

@pytest.mark.asyncio
async def test_not_found():
    resolver = ToolResolver()
    with pytest.raises(ToolNotFoundError):
        await resolver.resolve("nonexistent_tool_xyz")

@pytest.mark.asyncio
async def test_cache(monkeypatch):
    resolver = ToolResolver()
    resolved = await resolver.resolve("python3")
    monkeypatch.setattr("shutil.which", lambda x: "/not/real")
    resolved2 = await resolver.resolve("python3")
    assert resolved == resolved2
    
    # Second cached lookup for a failed tool
    resolver._resolved["python:fake_tool"] = None
    with pytest.raises(ToolNotFoundError):
        await resolver.resolve("fake_tool")

@pytest.mark.asyncio
async def test_is_available():
    resolver = ToolResolver()
    assert await resolver.is_available("python3")
    assert not await resolver.is_available("nonexistent_tool_xyz")

@pytest.mark.asyncio
async def test_node_ecosystem_local(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    dummy = bin_dir / "dummy"
    dummy.touch(mode=0o755)
    
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy", ecosystem="node")
    assert resolved == [str(Path("node_modules") / ".bin" / "dummy")]

@pytest.mark.asyncio
async def test_node_ecosystem_system(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/dummy_node")
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy", ecosystem="node")
    assert resolved == ["/usr/bin/dummy_node"]

@pytest.mark.asyncio
async def test_node_ecosystem_not_found():
    resolver = ToolResolver()
    with pytest.raises(ToolNotFoundError):
        await resolver.resolve("fake_node_tool", ecosystem="node")

@pytest.mark.asyncio
async def test_binary_ecosystem_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/dummy_bin")
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy", ecosystem="binary")
    assert resolved == ["/usr/bin/dummy_bin"]

@pytest.mark.asyncio
async def test_binary_ecosystem_not_found():
    resolver = ToolResolver()
    with pytest.raises(ToolNotFoundError):
        await resolver.resolve("fake_bin_tool", ecosystem="binary")

@pytest.mark.asyncio
async def test_module_fallback_timeout(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                pass
        return MockProc()
    
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    monkeypatch.setattr("asyncio.wait_for", lambda a, timeout: asyncio.sleep(0.01)) # we will mock the exception
    
    def mock_wait_for(aw, timeout):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio, "wait_for", mock_wait_for)
    
    resolver = ToolResolver()
    with pytest.raises(ToolNotFoundError):
        await resolver.resolve("some_module", ecosystem="python")

@pytest.mark.asyncio
async def test_system_path_mocked(monkeypatch):
    from core.infra.tool_resolver import ToolResolver
    monkeypatch.setattr("core.infra.tool_resolver.get_venv_python", lambda: None)
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/dummy_system_tool")
    
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy_system_tool")
    assert resolved == ["/usr/bin/dummy_system_tool"]
