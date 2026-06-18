"""
tests/primitives/test_commands_coverage.py

Coverage boosters for the command layer.  All assertions are validated against
the *actual* current implementation — no stale API references.
"""
import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from core.primitives.commands import CommandRegistry, CommandContext, Command
from core.primitives.settings import SettingsManager
from core.primitives.events import EventType


# ── Shared fixture ──────────────────────────────────────────────────────────

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
        privilege_level=2,  # OPERATOR
    )
    registry = CommandRegistry(sm)
    return registry, context, sm, proj


# ── _get_nested (lives in config handler) ──────────────────────────────────

def test_get_nested_dict_and_attr():
    """_get_nested is a module-level helper inside config.py."""
    from core.primitives.commands.handlers.config import _get_nested

    class Dummy:
        attr = "val"

    assert _get_nested({"a": {"b": 1}}, ["a", "b"]) == 1
    assert _get_nested(Dummy(), ["attr"]) == "val"
    assert _get_nested({"a": 1}, ["x"]) is None
    assert _get_nested(123, ["x"]) is None   # neither dict nor has-attr → None


# ── Registry basics ─────────────────────────────────────────────────────────

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
    assert "Unknown command" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_execute_empty_string(registry_and_context):
    """Empty input must return context unchanged without error."""
    reg, ctx, _, _ = registry_and_context
    before = list(ctx.stdout_buffer)
    await reg.execute("   ", ctx)
    assert ctx.stdout_buffer == before


@pytest.mark.asyncio
async def test_execute_privilege_denied(registry_and_context):
    """Executing an ADMIN command with READONLY privilege must deny access."""
    reg, ctx, _, _ = registry_and_context
    ctx.privilege_level = 0  # READONLY
    await reg.execute("project:register --path=.", ctx)
    assert ctx.has_error
    assert "Access denied" in ctx.stdout_buffer[-1]


# ── system:help ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_help_lists_commands(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:help", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "Available commands" in out


@pytest.mark.asyncio
async def test_system_help_specific_command(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:help exit", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "Usage:" in out or "usage" in out.lower()


@pytest.mark.asyncio
async def test_system_help_unknown_command(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:help no_such_cmd", ctx)
    assert ctx.has_error


@pytest.mark.asyncio
async def test_system_help_argparse_error(registry_and_context):
    """--help flag triggers argparse which writes an error to stdout_buffer."""
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:help --help", ctx)
    # argparse writes usage to stderr; the parser wraps it as an error in stdout_buffer
    assert len(ctx.stdout_buffer) > 0


# ── system:status ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_status_output(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("system:status", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "Privilege" in out


@pytest.mark.asyncio
async def test_handler_exception_caught(registry_and_context):
    """Any uncaught exception in a handler is caught and written as an error."""
    reg, ctx, _, _ = registry_and_context

    async def exploding_handler(c, p):
        raise RuntimeError("boom")

    reg.register(Command("boom", "desc", "boom", exploding_handler, 0))
    await reg.execute("boom", ctx)
    assert "boom" in ctx.stdout_buffer[-1]


# ── project handlers ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_project_register_valid(registry_and_context, tmp_path):
    reg, ctx, sm, proj = registry_and_context
    test_path = tmp_path / "new_sub"
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
async def test_handle_project_list_with_projects(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("project:list", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert proj.id[:8] in out


@pytest.mark.asyncio
async def test_handle_project_info_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:info bad_id", ctx)
    assert ctx.has_error
    assert "not found" in ctx.stdout_buffer[-1].lower()


@pytest.mark.asyncio
async def test_handle_project_info_active(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute(f"project:info {proj.id}", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert proj.name in out


@pytest.mark.asyncio
async def test_handle_project_info_no_id_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("project:info", ctx)
    assert ctx.has_error


@pytest.mark.asyncio
async def test_handle_project_clear_no_force(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:clear", ctx)
    assert ctx.has_error
    assert "--force" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_handle_project_clear_with_force(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:clear --force", ctx)
    assert "Cleared" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_handle_project_delete_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("project:delete nonexistent-id", ctx)
    assert ctx.has_error


# ── config handlers ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_get(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("config:get project_name", ctx)
    assert "test-project" in ctx.stdout_buffer[-1]

    ctx.has_error = False
    ctx.active_project = None
    await reg.execute("config:get project_name", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_config_set_nested_and_errors(registry_and_context):
    reg, ctx, sm, proj = registry_and_context

    # No active project
    ctx.active_project = None
    await reg.execute("config:set a.b true", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]

    # Valid nested set
    ctx.active_project = proj
    await reg.execute("config:set scanners.Bandit true", ctx)
    # Current implementation writes: "Set scanners.Bandit = True"
    assert "scanners.Bandit" in ctx.stdout_buffer[-1]
    assert "True" in ctx.stdout_buffer[-1]

    # Patch-level error
    with patch.object(sm, "patch_project_settings", side_effect=Exception("db err")):
        await reg.execute("config:set a b", ctx)
    assert "db err" in ctx.stdout_buffer[-1]


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


# ── audit handlers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_run_no_active_project(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("audit:run", ctx)
    assert ctx.has_error
    assert "No active project" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_audit_run_no_orchestrator(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    # orchestrator is None by default
    await reg.execute("audit:run", ctx)
    assert ctx.has_error
    assert "Orchestrator not available" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_audit_cancel_no_orchestrator(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:cancel", ctx)
    assert ctx.has_error
    assert "Orchestrator not available" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_audit_status_no_orchestrator(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("audit:status", ctx)
    assert ctx.has_error


@pytest.mark.asyncio
async def test_audit_history_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("audit:history", ctx)
    assert ctx.has_error


@pytest.mark.asyncio
async def test_audit_history_no_jobs_dir(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    # No jobs directory exists → "No audit history found."
    await reg.execute("audit:history", ctx)
    assert "No audit history found." in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_audit_history_with_summary(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs"
    job_dir = jobs_dir / "job-abc12345"
    job_dir.mkdir(parents=True)
    (job_dir / "audit_summary.json").write_text(
        json.dumps({"fleet_average": 9.5, "findings_count": 3})
    )
    await reg.execute("audit:history --limit=5", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "job-abc1" in out or "9.5" in out


@pytest.mark.asyncio
async def test_audit_history_unreadable_summary(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs"
    job_dir = jobs_dir / "job-bad00000"
    job_dir.mkdir(parents=True)
    (job_dir / "audit_summary.json").write_text("{corrupt")
    await reg.execute("audit:history --limit=5", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "summary unreadable" in out or "job-bad0" in out


@pytest.mark.asyncio
async def test_audit_history_no_summary_file(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs"
    job_dir = jobs_dir / "job-nos00000"
    job_dir.mkdir(parents=True)
    await reg.execute("audit:history --limit=5", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "no summary" in out or "job-nos0" in out


# ── scanner handlers ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scanner_config_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("scanner:config Bandit", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_scanner_config_set_strictness(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await reg.execute("scanner:config Bandit --strictness=high", ctx)
    # Current implementation: "Updated 'Bandit' scanner config."
    assert "Bandit" in ctx.stdout_buffer[-1]
    assert "scanner config" in ctx.stdout_buffer[-1].lower()


@pytest.mark.asyncio
async def test_scanner_config_show(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    # Set first, then read
    await reg.execute("scanner:config Bandit --strictness=medium", ctx)
    ctx.active_project = await sm.load_project(proj.id)
    await reg.execute("scanner:config Bandit", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "medium" in out


@pytest.mark.asyncio
async def test_scanner_enable_disable(registry_and_context):
    reg, ctx, sm, proj = registry_and_context
    await reg.execute("scanner:enable Bandit", ctx)
    assert "enabled" in ctx.stdout_buffer[-1]
    await reg.execute("scanner:disable Bandit", ctx)
    assert "disabled" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_scanner_install_python(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    # Use a known scanner name from the registry; fall back to a mock
    from core.infra.registry import PluginRegistry
    pr = PluginRegistry()
    pr.load()
    all_scanners = pr.all()
    if all_scanners:
        name = all_scanners[0].name
        await reg.execute(f"scanner:install {name}", ctx)
        out = "\n".join(ctx.stdout_buffer)
        assert "pip install" in out or "npm install" in out or "package manager" in out
    else:
        # No scanners registered — scanner not found path
        await reg.execute("scanner:install NonExistentScanner", ctx)
        assert ctx.has_error


@pytest.mark.asyncio
async def test_scanner_install_not_found(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    await reg.execute("scanner:install NoSuchScanner", ctx)
    assert ctx.has_error
    assert "not found" in ctx.stdout_buffer[-1].lower()


# ── fix handlers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fix_list_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("fix:list", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_fix_list_with_entries(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    fq_path = Path(proj.settings.project_path) / ".nexus_fix_queue.json"
    fq_path.write_text(json.dumps({
        "fingerprint-aaa": {"fingerprint": "fingerprint-aaa", "status": "done", "message": "msg"},
        "fingerprint-bbb": {"fingerprint": "fingerprint-bbb", "status": "open", "message": "msg"}
    }))
    await reg.execute("fix:list --status=done --limit=1", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "fingerprint-aaa"[:12] in out


@pytest.mark.asyncio
async def test_fix_list_no_matches(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("fix:list --status=done", ctx)
    assert "No findings match the filter." in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_fix_show_no_active(registry_and_context):
    reg, ctx, _, _ = registry_and_context
    ctx.active_project = None
    await reg.execute("fix:show f1", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_fix_show_found(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    from core.engines.fix_queue import FixQueue
    fq = FixQueue(Path(proj.settings.project_path) / ".nexus_fix_queue.json")
    await fq.update_status("fingerprint-xyz", "done")
    await reg.execute("fix:show fingerprint-xyz", ctx)
    assert "done" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_fix_show_not_found(registry_and_context):
    reg, ctx, _, proj = registry_and_context
    await reg.execute("fix:show nonexistent-finding", ctx)
    assert ctx.has_error
    assert "not found" in ctx.stdout_buffer[-1].lower()


# ── log handlers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_stream_no_orchestrator(registry_and_context):
    """log:stream without orchestrator should write an error."""
    reg, ctx, _, _ = registry_and_context
    await reg.execute("log:stream", ctx)
    assert ctx.has_error
    assert "Orchestrator not available" in ctx.stdout_buffer[-1]


@pytest.mark.asyncio
async def test_log_stream_no_follow(registry_and_context):
    """log:stream without --follow should print a hint."""
    reg, ctx, _, _ = registry_and_context
    mock_orch = MagicMock()
    ctx.orchestrator = mock_orch
    reg.orchestrator = mock_orch
    await reg.execute("log:stream", ctx)
    assert "--follow" in ctx.stdout_buffer[-1]


# ── report handlers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_history(registry_and_context, tmp_path):
    reg, ctx, _, proj = registry_and_context
    ctx.active_project = None
    await reg.execute("report:history", ctx)
    assert "No active project" in ctx.stdout_buffer[-1]

    ctx.active_project = proj
    history_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "audit_reports"
    history_dir.mkdir(parents=True)
    (history_dir / "r1.md").touch()
    (history_dir / "r2.md").touch()
    await reg.execute("report:history --limit=1", ctx)
    out = "\n".join(ctx.stdout_buffer)
    assert "r1.md" in out or "r2.md" in out


# ── no-parser command ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_click_parser(registry_and_context):
    reg, ctx, _, _ = registry_and_context

    async def dummy_handler(c, p):
        c.write("dummy-ok")

    reg.register(Command("dummy", "desc", "dummy", dummy_handler, 0, None))
    await reg.execute("dummy", ctx)
    assert "dummy-ok" in ctx.stdout_buffer[-1]
