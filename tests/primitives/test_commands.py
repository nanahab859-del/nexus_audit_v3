import pytest
import asyncio
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
    return registry, context, sm, proj

@pytest.mark.asyncio
async def test_all_commands_functional(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    
    commands = [
        ("system:version", []),
        ("system:help", []),
        ("system:help audit:run", []),
        ("system:clear", []),
        ("system:status", []),
        ("workspace:status", []),
        ("project:list", []),
        (f"project:info {proj.id}", []),
        ("config:show", []),
        ("config:export", []),
        ("scanner:list", []),
        ("scanner:enable bandit", []),
        ("scanner:disable bandit", []),
        ("fix:list", []),
        ("ai:status", []),
        ("ai:test", []),
    ]
    
    for cmd, args in commands:
        res = await reg.execute(cmd, ctx)
        assert not res.has_error, f"Command {cmd} failed"
        if cmd != "system:clear":
            assert len(res.stdout_buffer) > 0, f"Command {cmd} produced no output"

@pytest.mark.asyncio
async def test_privilege_enforcement(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.privilege_level = 0
    
    restricted = [
        ("audit:run", "Access denied"),
        ("config:set project_name val", "Access denied"),
        (f"project:delete {proj.id}", "Access denied"),
        ("ai:test", "Access denied")
    ]
    
    for cmd, expected_err in restricted:
        res = await reg.execute(cmd, ctx)
        assert res.has_error
        assert any(expected_err in line for line in res.stdout_buffer)

@pytest.mark.asyncio
async def test_alias_resolution(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("run", ctx)
    assert ctx.stdout_buffer[-1] != "[ERROR] Unknown command: run"

@pytest.mark.asyncio
async def test_config_set_logic(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await reg.execute("config:set project_name newname", ctx)
    
    updated_proj = await sm.load_project(proj.id)
    assert updated_proj.settings.project_name == "newname"

@pytest.mark.asyncio
async def test_handle_workspace_active_invalid_id(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("workspace:active non-existent", ctx)
    assert res.has_error

@pytest.mark.asyncio
async def test_handle_project_register_invalid_path(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("project:register --path=/invalid/path --name=test", ctx)
    assert res.has_error

@pytest.mark.asyncio
async def test_handle_project_delete_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("project:delete non-existent", ctx)
    assert res.has_error

@pytest.mark.asyncio
async def test_execute_no_input(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("   ", ctx)
    assert not res.has_error

@pytest.mark.asyncio
async def test_project_delete_missing_id(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    res = await reg.execute("project:delete", ctx)
    assert res.has_error
