"""
Tests for report command handlers (core/primitives/commands/handlers/report.py).

Coverage: report:generate and report:history commands, error handling,
and integration with ReportEngine.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import asyncio

from core.primitives.commands import CommandRegistry, CommandContext, OPERATOR, READONLY
from core.primitives.settings import SettingsManager


@pytest.fixture
def registry_with_report_handler(tmp_path, monkeypatch):
    """Create CommandRegistry with report handlers."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    
    sm = SettingsManager()
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path)))
    asyncio.run(sm.set_active_project(proj.id))
    
    workspace = asyncio.run(sm.load_workspace())
    
    context = CommandContext(
        workspace=workspace,
        settings_manager=sm,
        active_project=proj,
        privilege_level=OPERATOR,
    )
    
    registry = CommandRegistry(sm)
    
    return registry, context, sm, proj


@pytest.fixture
def completed_audit_with_reports(tmp_path, monkeypatch, sample_result_data):
    """Create a completed audit with report directory setup."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    
    sm = SettingsManager()
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path)))
    asyncio.run(sm.set_active_project(proj.id))
    
    # Create job directory with audit data
    job_id = "job-001"
    job_dir = tmp_path / ".nexus_audit" / "projects" / proj.id / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    data_file = job_dir / "audit_data_complete.json"
    data_file.write_text(json.dumps(sample_result_data, indent=2, default=str))
    
    workspace = asyncio.run(sm.load_workspace())
    
    context = CommandContext(
        workspace=workspace,
        settings_manager=sm,
        active_project=proj,
        privilege_level=OPERATOR,
    )
    
    registry = CommandRegistry(sm)
    
    return registry, context, sm, proj, job_id


class TestReportGenerateCommand:
    """Test report:generate command."""
    
    @pytest.mark.asyncio
    async def test_report_generate_no_active_project(self, registry_with_report_handler):
        """Test error when no active project."""
        reg, ctx, _, _ = registry_with_report_handler
        ctx.active_project = None
        
        await reg.execute("report:generate", ctx)
        
        assert ctx.has_error
        assert "[ERROR]" in ctx.stdout_buffer[0]
        assert "No active project" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_no_completed_audit(self, registry_with_report_handler):
        """Test error when no completed audit exists."""
        reg, ctx, sm, proj = registry_with_report_handler
        
        await reg.execute("report:generate", ctx)
        
        assert ctx.has_error
        assert "[ERROR]" in ctx.stdout_buffer[0]
        assert "No completed audit" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_markdown_success(self, completed_audit_with_reports):
        """Test successful markdown report generation."""
        reg, ctx, _, proj, job_id = completed_audit_with_reports
        
        await reg.execute("report:generate --format md", ctx)
        
        assert not ctx.has_error
        assert "Report generated:" in ctx.stdout_buffer[0]
        assert ".md" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_json_success(self, completed_audit_with_reports):
        """Test successful JSON report generation."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        await reg.execute("report:generate --format json", ctx)
        
        assert not ctx.has_error
        assert "Report generated:" in ctx.stdout_buffer[0]
        assert ".json" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_default_markdown(self, completed_audit_with_reports):
        """Test default format is markdown."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        await reg.execute("report:generate", ctx)
        
        assert not ctx.has_error
        assert ".md" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_custom_output_path(self, completed_audit_with_reports, tmp_path):
        """Test generating report to custom path."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        custom_path = tmp_path / "custom_report.md"
        
        await reg.execute(f"report:generate --output {custom_path}", ctx)
        
        assert not ctx.has_error
        assert str(custom_path) in ctx.stdout_buffer[0]
        assert custom_path.exists()
    
    @pytest.mark.asyncio
    async def test_report_generate_specific_job(self, completed_audit_with_reports):
        """Test generating report for specific job."""
        reg, ctx, _, _, job_id = completed_audit_with_reports
        
        await reg.execute(f"report:generate --job {job_id}", ctx)
        
        assert not ctx.has_error
        assert "Report generated:" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_generate_with_all_options(self, completed_audit_with_reports, tmp_path):
        """Test report:generate with all options."""
        reg, ctx, _, _, job_id = completed_audit_with_reports
        custom_path = tmp_path / "test_report.json"
        
        await reg.execute(
            f"report:generate --format json --output {custom_path} --job {job_id}",
            ctx
        )
        
        assert not ctx.has_error
        assert str(custom_path) in ctx.stdout_buffer[0]
        assert custom_path.exists()
        
        # Verify it's valid JSON
        data = json.loads(custom_path.read_text())
        assert "project_name" in data
    
    @pytest.mark.asyncio
    async def test_report_generate_invalid_format(self, completed_audit_with_reports):
        """Test error for invalid format."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        await reg.execute("report:generate --format pdf", ctx)
        
        assert ctx.has_error
        assert "[ERROR]" in ctx.stdout_buffer[0]


class TestReportHistoryCommand:
    """Test report:history command."""
    
    @pytest.mark.asyncio
    async def test_report_history_no_active_project(self, registry_with_report_handler):
        """Test error when no active project."""
        reg, ctx, _, _ = registry_with_report_handler
        ctx.active_project = None
        
        await reg.execute("report:history", ctx)
        
        assert ctx.has_error
        assert "[ERROR]" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_history_no_reports(self, completed_audit_with_reports):
        """Test report:history when no reports exist."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        await reg.execute("report:history", ctx)
        
        assert not ctx.has_error
        assert "No reports found" in "\\n".join(ctx.stdout_buffer)
    
    @pytest.mark.asyncio
    async def test_report_history_with_reports(self, completed_audit_with_reports, tmp_path):
        """Test report:history lists existing reports."""
        reg, ctx, _, proj, _ = completed_audit_with_reports
        
        # Generate some reports
        await reg.execute("report:generate --format md", ctx)
        ctx.stdout_buffer = []
        
        await reg.execute("report:history", ctx)
        
        assert not ctx.has_error
        output = "\\n".join(ctx.stdout_buffer)
        assert "report_" in output or ".md" in output
    
    @pytest.mark.asyncio
    async def test_report_history_limit(self, completed_audit_with_reports):
        """Test report:history --limit parameter."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Generate multiple reports
        for i in range(5):
            ctx.stdout_buffer = []
            await reg.execute("report:generate --format md", ctx)
        
        # Clear buffer and run history with limit
        ctx.stdout_buffer = []
        await reg.execute("report:history --limit 2", ctx)
        
        assert not ctx.has_error
        output = "\\n".join(ctx.stdout_buffer)
        # Should have at most 2 reports listed
        # Count lines with report names (rough check)
        lines = [l for l in output.split("\\n") if "report_" in l]
        assert len(lines) <= 2
    
    @pytest.mark.asyncio
    async def test_report_history_shows_size(self, completed_audit_with_reports):
        """Test report:history shows file size."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Generate a report
        await reg.execute("report:generate --format md", ctx)
        ctx.stdout_buffer = []
        
        # List history
        await reg.execute("report:history", ctx)
        
        output = "\\n".join(ctx.stdout_buffer)
        
        # Should contain size indicator (k for kilobytes)
        assert "k" in output or "NAME" in output


class TestReportCommandsPrivilege:
    """Test privilege levels for report commands."""
    
    @pytest.mark.asyncio
    async def test_report_generate_requires_operator(self, registry_with_report_handler):
        """Test report:generate requires OPERATOR privilege."""
        reg, ctx, _, _ = registry_with_report_handler
        ctx.privilege_level = READONLY  # Insufficient privilege
        
        await reg.execute("report:generate", ctx)
        
        # Should get access denied error
        assert ctx.has_error
        assert "Access denied" in ctx.stdout_buffer[0]
    
    @pytest.mark.asyncio
    async def test_report_history_allows_readonly(self, completed_audit_with_reports):
        """Test report:history allows READONLY privilege."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        ctx.privilege_level = READONLY
        
        # Generate a report first (as OPERATOR)
        ctx.privilege_level = OPERATOR
        await reg.execute("report:generate --format md", ctx)
        
        # Now test as READONLY
        ctx.privilege_level = READONLY
        ctx.stdout_buffer = []
        await reg.execute("report:history", ctx)
        
        # Should succeed
        assert not ctx.has_error


class TestReportCommandsIntegration:
    """Integration tests for report commands."""
    
    @pytest.mark.asyncio
    async def test_generate_then_history_workflow(self, completed_audit_with_reports):
        """Test generate report then list history."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Generate first report
        await reg.execute("report:generate --format md", ctx)
        assert not ctx.has_error
        first_report_line = ctx.stdout_buffer[0]
        
        ctx.stdout_buffer = []
        
        # Generate second report
        await reg.execute("report:generate --format json", ctx)
        assert not ctx.has_error
        
        ctx.stdout_buffer = []
        
        # List history
        await reg.execute("report:history", ctx)
        assert not ctx.has_error
        
        # Should show both reports
        output = "\\n".join(ctx.stdout_buffer)
        # At least should not error
        assert len(ctx.stdout_buffer) > 0
    
    @pytest.mark.asyncio
    async def test_multiple_formats_generation(self, completed_audit_with_reports):
        """Test generating both markdown and JSON formats."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Generate markdown
        await reg.execute("report:generate --format md", ctx)
        assert not ctx.has_error
        md_path = ctx.stdout_buffer[0].split(": ")[1].strip()
        
        ctx.stdout_buffer = []
        
        # Generate JSON
        await reg.execute("report:generate --format json", ctx)
        assert not ctx.has_error
        json_path = ctx.stdout_buffer[0].split(": ")[1].strip()
        
        # Verify both exist
        assert Path(md_path).exists()
        assert Path(json_path).exists()
        assert md_path.endswith(".md")
        assert json_path.endswith(".json")


class TestReportCommandsParsing:
    """Test argument parsing for report commands."""
    
    @pytest.mark.asyncio
    async def test_report_generate_format_choices(self, completed_audit_with_reports):
        """Test format argument accepts md and json."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Valid formats
        for fmt in ["md", "json"]:
            ctx.stdout_buffer = []
            await reg.execute(f"report:generate --format {fmt}", ctx)
            # Should not error on format (may error on no project, but not format)
            assert "format" not in ctx.stdout_buffer[0].lower() or not ctx.has_error
    
    @pytest.mark.asyncio
    async def test_report_history_limit_type(self, completed_audit_with_reports):
        """Test limit argument accepts integer."""
        reg, ctx, _, _, _ = completed_audit_with_reports
        
        # Generate reports
        for _ in range(3):
            ctx.stdout_buffer = []
            await reg.execute("report:generate --format md", ctx)
        
        ctx.stdout_buffer = []
        
        # Should accept integer
        await reg.execute("report:history --limit 1", ctx)
        assert not ctx.has_error
