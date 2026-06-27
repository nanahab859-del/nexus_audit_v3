import pytest
import asyncio
import json
from core.primitives.commands import CommandRegistry, CommandContext
from core.primitives.settings import SettingsManager

@pytest.fixture
def registry_and_context(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sm = SettingsManager()
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path)))
    asyncio.run(sm.set_active_project(proj.id))
    context = CommandContext(
        workspace=asyncio.run(sm.load_workspace()),
        settings_manager=sm,
        active_project=proj,
        privilege_level=2,
    )
    registry = CommandRegistry(sm)
    yield registry, context, sm, proj
    try:
        asyncio.run(sm.delete_project(proj.id))
    except Exception:
        pass

@pytest.mark.asyncio
async def test_mcp_status_missing(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("mcp:status", ctx)
    assert not res.has_error
    assert any("NOT present" in line for line in res.stdout_buffer)

@pytest.mark.asyncio
async def test_mcp_config_creates_entry(registry_and_context, tmp_path):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("mcp:config", ctx)
    assert not res.has_error
    assert any("configuration written" in line for line in res.stdout_buffer)
    
    ctx.stdout_buffer.clear()
    res = await reg.execute("mcp:status", ctx)
    assert not res.has_error
    assert any("PRESENT" in line for line in res.stdout_buffer)
