import pytest
import asyncio
from core.primitives.commands import CommandRegistry, CommandContext
from core.primitives.settings import SettingsManager
from core.primitives.events import EventType

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
async def test_require_privilege_decorator_direct(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    ctx.privilege_level = 0
    await reg._handle_workspace_active(ctx, {})
    assert "Access denied" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_get_nested(registry_and_context):
    from core.primitives.commands import _get_nested
    class Dummy:
        attr = "val"
    assert _get_nested({"a": {"b": 1}}, ["a", "b"]) == 1
    assert _get_nested(Dummy(), ["attr"]) == "val"
    assert _get_nested({"a": 1}, ["x"]) is None
    assert _get_nested(123, ["x"]) is None

@pytest.mark.asyncio
async def test_registry_list_all(registry_and_context):
    reg, _, _, _ = registry_and_context
    assert len(reg.list_all()) > 0

@pytest.mark.asyncio
async def test_execute_shlex_error(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute('run "', ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_execute_unknown_command(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("unknown_cmd", ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_execute_click_exit(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:help --help", ctx)
    assert "Usage:" in "".join(ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_execute_click_exception(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    import click
    from unittest.mock import patch
    with patch.object(click.Command, 'make_context', side_effect=Exception("mocked err")):
        await reg.execute("system:status", ctx)
    assert "mocked err" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_handle_workspace_active_valid(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await reg.execute(f"workspace:active {proj.id}", ctx)
    assert "Active project set to" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_handle_project_register_valid(registry_and_context, tmp_path):
    reg, ctx, sm, proj = registry_and_context
    test_path = tmp_path / "test"
    test_path.mkdir(parents=True, exist_ok=True)
    await reg.execute(f"project:register --path={test_path} --name=new_proj", ctx)
    assert "registered at" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_handle_project_list_empty(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    ctx.workspace.projects.clear()
    await reg.execute("project:list", ctx)
    assert "No projects registered." in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_handle_project_info_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:info bad_id", ctx)
    assert "Project not found" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_handle_project_clear(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:clear", ctx)
    assert "Run with --force" in ctx.stdout_buffer[-1]
    await reg.execute("project:clear --force", ctx)
    assert "Cleared" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_audit_stubs(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:run", ctx)
    assert "[INFO] Feature 'audit:run' is currently a stub." in ctx.stdout_buffer[-1]
    await reg.execute("audit:cancel", ctx)
    assert "stub" in ctx.stdout_buffer[-1]
    await reg.execute("audit:status", ctx)
    assert "stub" in ctx.stdout_buffer[-1]
    await reg.execute("audit:history", ctx)
    assert "stub" in ctx.stdout_buffer[-1]
    await reg.execute("report:generate", ctx)
    assert "stub" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_config_get(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("config:get project_name", ctx)
    assert "test-project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = None
    await reg.execute("config:get project_name", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_config_set_nested_and_errors(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("config:set a.b true", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    await reg.execute("config:set scanners.Bandit true", ctx)
    assert "Set scanners.Bandit to True" in ctx.stdout_buffer[-1]
    
    from unittest.mock import patch
    with patch.object(sm, 'patch_project_settings', side_effect=Exception("db err")):
        await reg.execute("config:set a b", ctx)
    assert "Failed to set config: db err" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_config_show_section(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("config:show", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    await reg.execute("config:show --section=project_name", ctx)
    assert "test-project" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_config_export_path(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("config:export", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    out = tmp_path / "out.json"
    await reg.execute(f"config:export --path={out}", ctx)
    assert "Exported to" in ctx.stdout_buffer[-1]
    assert out.exists()

@pytest.mark.asyncio
async def test_scanner_config(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("scanner:config Bandit", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    await reg.execute("scanner:config Bandit --strictness=high", ctx)
    assert "Updated Bandit config" in ctx.stdout_buffer[-1]
    
    ctx.active_project = await registry_and_context[2].load_project(proj.id)
    await reg.execute("scanner:config Bandit", ctx)
    assert "high" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_fix_list_args(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("fix:list", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    from core.engines.fix_queue import FixQueue
    from pathlib import Path
    fq = FixQueue(Path(proj.settings.project_path) / ".nexus_fix_queue.json")
    await fq.update_status("f1", "done")
    await fq.update_status("f2", "open")
    await fq.update_status("f3", "done")
    await reg.execute("fix:list --status=done --limit=1", ctx)
    out = "".join(ctx.stdout_buffer)
    assert "f1" in out
    assert "f3" not in out

@pytest.mark.asyncio
async def test_fix_show(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("fix:show f1", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    from core.engines.fix_queue import FixQueue
    from pathlib import Path
    fq = FixQueue(Path(proj.settings.project_path) / ".nexus_fix_queue.json")
    await fq.update_status("f1", "done")
    await reg.execute("fix:show f1", ctx)
    assert "done" in ctx.stdout_buffer[-1]
    await reg.execute("fix:show nonexist", ctx)
    assert "Finding not found" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_report_history(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("report:history", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    from pathlib import Path
    history_dir = Path.home() / ".nexus_audit" / "projects" / proj.id / "audit_reports"
    history_dir.mkdir(parents=True)
    (history_dir / "r1.md").touch()
    (history_dir / "r2.md").touch()
    await reg.execute("report:history --limit=1", ctx)
    out = "".join(ctx.stdout_buffer)
    assert "r1.md" in out or "r2.md" in out

@pytest.mark.asyncio
async def test_log_stream(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    import asyncio
    async def run_with_cancel():
        t = asyncio.create_task(reg.execute("log:stream --follow", ctx))
        await asyncio.sleep(0.01)
        
        class MockEvent:
            type = "info"
            data = "testmsg"
        
        for sub in reg.orchestrator.bus._subscribers.get(EventType.LOG, []):
            sub(MockEvent())
            
        await asyncio.sleep(0.01)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    await run_with_cancel()
    out = "".join(ctx.stdout_buffer)
    assert "testmsg" in out

@pytest.mark.asyncio
async def test_history_clear(registry_and_context, monkeypatch):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("history:clear", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]
    
    ctx.active_project = proj
    
    monkeypatch.setattr("click.confirm", lambda msg: False)
    await reg.execute("history:clear", ctx)
    assert "Aborted" in ctx.stdout_buffer[-1]
    
    def raise_abort(*args):
        import click
        raise click.exceptions.Abort()
    monkeypatch.setattr("click.confirm", raise_abort)
    await reg.execute("history:clear", ctx)
    assert "Aborted" in ctx.stdout_buffer[-1]
    
    from pathlib import Path
    history_dir = Path.home() / ".nexus_audit" / "projects" / proj.id / "jobs"
    history_dir.mkdir(parents=True, exist_ok=True)
    await reg.execute("history:clear --force", ctx)
    assert "History cleared" in ctx.stdout_buffer[-1]
    assert not history_dir.exists()

@pytest.mark.asyncio
async def test_no_click_parser(registry_and_context):
    from core.primitives.commands import Command
    reg, ctx, _, _ = registry_and_context
    async def dummy_handler(c, p):
        c.write("dummy")
    reg.register(Command("dummy", "desc", "dummy", dummy_handler, 0, None))
    await reg.execute("dummy", ctx)
    assert "dummy" in ctx.stdout_buffer[-1]
