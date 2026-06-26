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
    return registry, context, sm, proj

@pytest.mark.asyncio
async def test_rebuild_index_no_project(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    res = await reg.execute("audit:rebuild-index", ctx)
    assert res.has_error
    assert any("Failed to rebuild index" in line for line in res.stdout_buffer)

@pytest.mark.asyncio
async def test_rebuild_index_success(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs"
    job_dir = jobs_dir / "job1"
    job_dir.mkdir(parents=True, exist_ok=True)
    summary = {"job_id": "job1", "timestamp": "2023-10-01T12:00:00Z"}
    with open(job_dir / "audit_summary.json", "w") as f:
        json.dump(summary, f)
        
    res = await reg.execute("audit:rebuild-index", ctx)
    assert res.has_error
    assert any("Failed to rebuild index" in line for line in res.stdout_buffer)

@pytest.mark.asyncio
async def test_rebuild_index_privilege(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.privilege_level = 0
    res = await reg.execute("audit:rebuild-index", ctx)
    assert res.has_error
    assert any("Access denied" in line for line in res.stdout_buffer)
