"""
Tests for ReportEngine class (core/reports/report_engine.py).

Coverage: Report engine initialization, job discovery, report generation,
and error handling for both markdown and JSON formats.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

from core.reports import ReportEngine


class TestReportEngineInitialization:
    """Test ReportEngine initialization."""
    
    def test_init_with_projects_dir(self, tmp_projects_dir):
        """Test ReportEngine initialization with projects directory."""
        engine = ReportEngine(tmp_projects_dir)
        assert engine._projects_dir == tmp_projects_dir
    
    def test_init_creates_instance(self, tmp_path):
        """Test that ReportEngine instance is properly created."""
        engine = ReportEngine(tmp_path)
        assert isinstance(engine, ReportEngine)
        assert hasattr(engine, "_projects_dir")
        assert hasattr(engine, "generate")
        assert hasattr(engine, "list_reports")
        assert hasattr(engine, "_load_result")


class TestLoadResult:
    """Test ReportEngine._load_result() method."""
    
    @pytest.mark.asyncio
    async def test_load_result_latest_job(self, tmp_projects_dir, completed_job_dir):
        """Test loading the latest job result."""
        jobs_dir, original_data = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        result_data, resolved_job_id = await engine._load_result(project_id, None)
        
        assert result_data is not None
        assert "metadata" in result_data
        assert "apps" in result_data
        assert resolved_job_id == "job-001"
    
    @pytest.mark.asyncio
    async def test_load_result_specific_job(self, multiple_jobs_dir, tmp_projects_dir):
        """Test loading a specific job by ID."""
        jobs_dir, jobs_by_id = multiple_jobs_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        # Load specific job
        result_data, resolved_job_id = await engine._load_result(project_id, "job-001")
        
        assert resolved_job_id == "job-001"
        assert result_data["metadata"]["job_id"] == "job-001"
    
    @pytest.mark.asyncio
    async def test_load_result_no_jobs_directory(self, tmp_path):
        """Test error when jobs directory doesn't exist."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        
        engine = ReportEngine(projects_dir)
        
        with pytest.raises(FileNotFoundError, match="No jobs directory"):
            await engine._load_result("nonexistent-project", None)
    
    @pytest.mark.asyncio
    async def test_load_result_job_not_found(self, completed_job_dir, tmp_projects_dir):
        """Test error when specific job doesn't exist."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        with pytest.raises(FileNotFoundError, match="Job 'nonexistent' not found"):
            await engine._load_result(project_id, "nonexistent")
    
    @pytest.mark.asyncio
    async def test_load_result_no_completed_audit(self, tmp_projects_dir):
        """Test error when no completed audits exist."""
        projects_dir = tmp_projects_dir.parent
        project_id = "project-no-audits"
        project_dir = projects_dir / project_id
        project_dir.mkdir()
        
        engine = ReportEngine(projects_dir)
        
        with pytest.raises(FileNotFoundError, match="No completed audit found"):
            await engine._load_result(project_id, None)
    
    @pytest.mark.asyncio
    async def test_load_result_empty_json_file(self, tmp_projects_dir):
        """Test error when audit_data_complete.json is empty."""
        project_id = "project-empty-audit"
        job_id = "job-empty"
        
        job_dir = tmp_projects_dir / project_id / "jobs" / job_id
        job_dir.mkdir(parents=True)
        
        # Create empty JSON file
        (job_dir / "audit_data_complete.json").write_text("{}")
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        with pytest.raises(FileNotFoundError, match="audit_data_complete.json empty or missing"):
            await engine._load_result(project_id, job_id)


class TestReportGeneration:
    """Test ReportEngine.generate() method."""
    
    @pytest.mark.asyncio
    async def test_generate_markdown_report(self, completed_job_dir, tmp_projects_dir):
        """Test generating a markdown report."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        output_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md"
        )
        
        assert output_path.exists()
        assert output_path.suffix == ".md"
        assert "Test Project" in output_path.read_text()
        assert "Fleet Health" in output_path.read_text()
    
    @pytest.mark.asyncio
    async def test_generate_json_report(self, completed_job_dir, tmp_projects_dir):
        """Test generating a JSON report."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        output_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="json"
        )
        
        assert output_path.exists()
        assert output_path.suffix == ".json"
        
        # Verify JSON is valid
        data = json.loads(output_path.read_text())
        assert data["project_name"] == "Test Project"
        assert "metadata" in data
    
    @pytest.mark.asyncio
    async def test_generate_with_custom_output_path(self, completed_job_dir, tmp_projects_dir, tmp_path):
        """Test generating report to custom path."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        custom_path = tmp_path / "custom_report.md"
        
        output_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md",
            output_path=custom_path
        )
        
        assert output_path == custom_path
        assert output_path.exists()
    
    @pytest.mark.asyncio
    async def test_generate_with_specific_job(self, multiple_jobs_dir, tmp_projects_dir):
        """Test generating report for a specific job."""
        jobs_dir, _ = multiple_jobs_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        output_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md",
            job_id="job-001"
        )
        
        assert output_path.exists()
        assert "job-001" in output_path.read_text()
    
    @pytest.mark.asyncio
    async def test_generate_unsupported_format(self, completed_job_dir, tmp_projects_dir):
        """Test error for unsupported format."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        with pytest.raises(ValueError, match="Unsupported format"):
            await engine.generate(
                project_id=project_id,
                project_name="Test Project",
                fmt="pdf"
            )
    
    @pytest.mark.asyncio
    async def test_generate_auto_naming(self, completed_job_dir, tmp_projects_dir):
        """Test auto-generated report filename includes timestamp."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        output_path1 = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md"
        )
        
        # Second report should have different timestamp
        output_path2 = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md"
        )
        
        assert output_path1.name != output_path2.name
        assert output_path1.parent == output_path2.parent


class TestListReports:
    """Test ReportEngine.list_reports() method."""
    
    @pytest.mark.asyncio
    async def test_list_reports_empty(self, completed_job_dir, tmp_projects_dir):
        """Test listing reports when none exist."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        reports = await engine.list_reports(project_id)
        
        assert reports == []
    
    @pytest.mark.asyncio
    async def test_list_reports_multiple(self, completed_job_dir, tmp_projects_dir):
        """Test listing multiple reports."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        # Generate multiple reports
        for i in range(3):
            await engine.generate(
                project_id=project_id,
                project_name="Test Project",
                fmt="md"
            )
        
        reports = await engine.list_reports(project_id)
        
        assert len(reports) == 3
        # Should be sorted by mtime (newest first)
        assert reports[0].stat().st_mtime >= reports[-1].stat().st_mtime
    
    @pytest.mark.asyncio
    async def test_list_reports_no_project(self, tmp_projects_dir):
        """Test listing reports when project doesn't exist."""
        engine = ReportEngine(tmp_projects_dir.parent)
        
        reports = await engine.list_reports("nonexistent-project")
        
        assert reports == []


class TestReportEngineErrorHandling:
    """Test error handling in ReportEngine."""
    
    @pytest.mark.asyncio
    async def test_generate_with_corrupted_json(self, tmp_projects_dir):
        """Test error handling with corrupted JSON data."""
        project_id = "project-corrupted"
        job_id = "job-corrupted"
        
        job_dir = tmp_projects_dir / project_id / "jobs" / job_id
        job_dir.mkdir(parents=True)
        
        # Write invalid JSON
        (job_dir / "audit_data_complete.json").write_text("{ invalid json }")
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        with pytest.raises(Exception):  # JSON decode error
            await engine.generate(
                project_id=project_id,
                project_name="Test Project",
                fmt="md"
            )
    
    @pytest.mark.asyncio
    async def test_generate_permission_error_on_write(self, completed_job_dir, tmp_projects_dir, monkeypatch):
        """Test error handling when unable to write report."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        # Mock Path.write_text to raise permission error
        original_write_text = Path.write_text
        
        def mock_write_text(self, *args, **kwargs):
            if "report_" in str(self):
                raise PermissionError("Permission denied")
            return original_write_text(self, *args, **kwargs)
        
        monkeypatch.setattr(Path, "write_text", mock_write_text)
        
        with pytest.raises(PermissionError):
            await engine.generate(
                project_id=project_id,
                project_name="Test Project",
                fmt="md"
            )


class TestReportEngineIntegration:
    """Integration tests for ReportEngine."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_markdown(self, completed_job_dir, tmp_projects_dir):
        """Test complete workflow: generate and list reports."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        # Generate reports
        for i in range(2):
            await engine.generate(
                project_id=project_id,
                project_name="Test Project",
                fmt="md"
            )
        
        # List reports
        reports = await engine.list_reports(project_id)
        assert len(reports) == 2
        
        # Verify content
        for report in reports:
            content = report.read_text()
            assert "Test Project" in content
            assert "Fleet Health" in content
    
    @pytest.mark.asyncio
    async def test_full_workflow_json(self, completed_job_dir, tmp_projects_dir):
        """Test complete workflow with JSON format."""
        jobs_dir, _ = completed_job_dir
        project_id = jobs_dir.parent.name
        
        engine = ReportEngine(tmp_projects_dir.parent)
        
        # Generate JSON and markdown
        md_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="md"
        )
        
        json_path = await engine.generate(
            project_id=project_id,
            project_name="Test Project",
            fmt="json"
        )
        
        # List reports
        reports = await engine.list_reports(project_id)
        assert len(reports) == 2
        
        # Verify formats
        assert json_path.suffix == ".json"
        assert md_path.suffix == ".md"
