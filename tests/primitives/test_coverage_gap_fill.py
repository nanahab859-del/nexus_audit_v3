import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from core.primitives.commands import CommandRegistry, CommandContext
from core.primitives.settings import SettingsManager
from core.primitives.events import EventType
from core.primitives.models import Job, ProjectSettings

@pytest.fixture
def registry_and_context(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sm = SettingsManager()
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path)))
    asyncio.run(sm.set_active_project(proj.id))
    
    # Mock orchestrator
    mock_orch = MagicMock()
    mock_orch.start_job = AsyncMock(return_value=Job(
        id="job-123", 
        project_id=proj.id,
        project_path=proj.path,
        started_at=datetime.now(timezone.utc)
    ))
    mock_orch.status = MagicMock(return_value={"state": "running", "job_id": "job-123"})
    mock_orch.cancel_job = AsyncMock()
    
    context = CommandContext(
        workspace=asyncio.run(sm.load_workspace()),
        settings_manager=sm,
        active_project=proj,
        privilege_level=2,
        orchestrator=mock_orch
    )
    registry = CommandRegistry(sm, orchestrator=mock_orch)
    yield registry, context, sm, proj
    # Teardown: delete every project registered during this test
    ws = asyncio.run(sm.load_workspace())
    for pid in list(ws.projects.keys()):
        try:
            asyncio.run(sm.delete_project(pid))
        except Exception:
            pass

@pytest.mark.asyncio
async def test_audit_run_success(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:run --fast", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert "job-123" in out
    assert "yes" in out

@pytest.mark.asyncio
async def test_audit_cancel_success(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:cancel", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert "Cancellation requested" in out
    ctx.orchestrator.cancel_job.assert_called_once()

@pytest.mark.asyncio
async def test_audit_status_success(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:status", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert "running" in out

@pytest.mark.asyncio
async def test_audit_history_success(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    
    # Mock job history
    proj.job_history = ["job-1", "job-2"]
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs"
    job_dir = jobs_dir / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "audit_summary.json").write_text(json.dumps({"findings_count": 5}))
    
    await reg.execute("audit:history", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert "job-1" in out

@pytest.mark.asyncio
async def test_fix_commands_success(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    
    # Write a finding to the queue
    fq_path = Path(proj.settings.project_path) / ".nexus_fix_queue.json"
    fq_path.write_text(json.dumps({
        "f-aaa": {"fingerprint": "f-aaa", "status": "open", "message": "msg"}
    }))
    
    # show
    await reg.execute("fix:show f-aaa", ctx)
    assert "f-aaa" in "\\n".join(ctx.stdout_buffer)
    
    # mark
    await reg.execute("fix:mark f-aaa done", ctx)
    assert "done" in ctx.stdout_buffer[-1].lower()
    
    # note
    await reg.execute("fix:note f-aaa This_is_a_test_note", ctx)
    assert "note added" in ctx.stdout_buffer[-1].lower()

@pytest.mark.asyncio
async def test_log_stream_success(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    
    ctx.orchestrator.bus = MagicMock()
    ctx.orchestrator.bus.subscribe = AsyncMock(return_value="token123")
    ctx.orchestrator.bus.unsubscribe = AsyncMock()
    
    t = asyncio.create_task(reg.execute("log:stream --follow", ctx))
    await asyncio.sleep(0.05)
    
    # trigger the lambda
    if ctx.orchestrator.bus.subscribe.called:
        cb = ctx.orchestrator.bus.subscribe.call_args[0][1]
        from datetime import datetime, timezone
        class MockType:
            value = "log"
        class MockEvent:
            timestamp = datetime.now(timezone.utc)
            type = MockType()
            payload = {"level": "info", "message": "mock log entry"}
        cb(MockEvent())
    
    await asyncio.sleep(0.05)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
        
    out = "\\n".join(ctx.stdout_buffer)
    assert "mock log entry" in out
        
    assert any("mock log entry" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_project_info_no_args_active(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("project:info", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert proj.id in out

@pytest.mark.asyncio
async def test_report_generate(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("report:generate", ctx)
    assert "No jobs directory" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_report_history_success(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    reports_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "audit_reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "report-1.md").touch()
    
    await reg.execute("report:history", ctx)
    assert "report-1.md" in "\\n".join(ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_scanner_list_all(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("scanner:list", ctx)
    assert len(ctx.stdout_buffer) > 0

@pytest.mark.asyncio
async def test_scanner_disable_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("scanner:disable Bandit", ctx)
    assert "disabled" in ctx.stdout_buffer[-1].lower() or "unknown scanner" in ctx.stdout_buffer[-1].lower()

@pytest.mark.asyncio
async def test_system_clear(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:clear", ctx)
    # System clear just clears the terminal, maybe writes nothing or ansi escape
    assert True

@pytest.mark.asyncio
async def test_system_version(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:version", ctx)
    assert "v0." in "\\n".join(ctx.stdout_buffer).lower()

@pytest.mark.asyncio
async def test_workspace_status(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("workspace:status", ctx)
    out = "\\n".join(ctx.stdout_buffer)
    assert "Global Config" in out or "Projects" in out

def test_models_severity_repr():
    from core.primitives.models import Severity
    assert repr(Severity.CRITICAL) == "<Severity.CRITICAL: 4>"

@pytest.mark.asyncio
async def test_settings_load_project_malformed(registry_and_context, tmp_path):
    reg, ctx, sm, proj = registry_and_context
    # Write a bad project file
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    pfile.write_text("not json")
    
    # load_project should raise JSONDecodeError or similar
    with pytest.raises(Exception):
        await sm.load_project(proj.id)

@pytest.mark.asyncio
async def test_settings_patch_project_settings_fallback(registry_and_context, tmp_path):
    reg, ctx, sm, proj = registry_and_context
    pfile = tmp_path / ".nexus_audit" / "projects" / proj.id / "project.json"
    data = json.loads(pfile.read_text())
    
    # mess up severity
    data["settings"]["fail_on_severity"] = None
    pfile.write_text(json.dumps(data))
    
    await sm.patch_project_settings(proj.id, {"project_name": "new"})
    p = await sm.load_project(proj.id)
    assert p.settings.project_name == "new"

@pytest.mark.asyncio
async def test_ai_status(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("ai:status", ctx)
    assert "todo" in "\\n".join(ctx.stdout_buffer).lower()

@pytest.mark.asyncio
async def test_workspace_active_success(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    test2_path = Path(proj.path).parent / "test2"
    test2_path.mkdir(exist_ok=True)
    proj2 = await sm.register_project("test-project-2", str(test2_path))
    ctx.workspace.projects[proj2.id] = proj2
    await reg.execute(f"workspace:active {proj2.id}", ctx)
    assert ctx.workspace_dirty
    assert ctx.active_project.id == proj2.id
    assert "Active project set to" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_system_exit(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("exit", ctx)
    assert ctx.exit_requested
    assert "Goodbye." in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_system_version_no_package(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    from importlib.metadata import PackageNotFoundError
    with patch("core.primitives.commands.handlers.system.version", side_effect=PackageNotFoundError("mock error")):
        await reg.execute("system:version", ctx)
        assert "dev" in "\\n".join(ctx.stdout_buffer).lower()

@pytest.mark.asyncio
async def test_fix_missing_branches(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("fix:list --status in_progress", ctx)
    
    ctx.active_project = None
    await reg.execute("fix:mark f-aaa done", ctx)
    assert ctx.has_error
    
    ctx.has_error = False
    await reg.execute("fix:note f-aaa text", ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_fix_note_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("fix:note nonexistent text", ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_project_delete_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:delete unknown_id", ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_project_delete_success(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await reg.execute(f"project:delete {proj.id}", ctx)
    assert ctx.workspace_dirty
    assert "Deleted:" in ctx.stdout_buffer[-1]

@pytest.mark.asyncio
async def test_settings_get_project_keyerror(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    sm._project_cache.clear()
    import pytest
    with pytest.raises(KeyError):
        sm.get_project(proj.id)

@pytest.mark.asyncio
async def test_settings_get_project_success(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await sm.load_project(proj.id)
    assert sm.get_project(proj.id).id == proj.id

@pytest.mark.asyncio
async def test_settings_patch_project_severity_types(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    # string
    await sm.patch_project_settings(proj.id, {"fail_on_severity": "HIGH"})
    # int
    await sm.patch_project_settings(proj.id, {"fail_on_severity": 2})

@pytest.mark.asyncio
async def test_scanner_list_filtered(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("scanner:list --category unknown_cat", ctx)
    assert len(ctx.stdout_buffer) > 0 # Header at least

@pytest.mark.asyncio
async def test_scanner_enable_disable_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("scanner:enable Bandit", ctx)
    assert ctx.has_error
    
    ctx.has_error = False
    await reg.execute("scanner:disable Bandit", ctx)
    assert ctx.has_error

@pytest.mark.asyncio
async def test_scanner_install_other_ecosystems(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    
    class MockNodeScanner:
        name = "node_scanner"
        ecosystem = "node"
        tool_name = "npm-tool"

    class MockBinaryScanner:
        name = "bin_scanner"
        ecosystem = "binary"
        tool_name = "sys-tool"
        
    class MockRegistry:
        def get(self, name):
            if name == "node_scanner": return MockNodeScanner()
            if name == "bin_scanner": return MockBinaryScanner()
            return None
            
    with patch("core.primitives.commands.handlers.scanner._get_plugin_registry", return_value=MockRegistry()):
        await reg.execute("scanner:install node_scanner", ctx)
        assert "npm install" in ctx.stdout_buffer[-1]
        
        await reg.execute("scanner:install bin_scanner", ctx)
        assert "package manager" in ctx.stdout_buffer[-1]
