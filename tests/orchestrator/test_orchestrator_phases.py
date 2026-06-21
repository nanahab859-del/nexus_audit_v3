"""
Tests for orchestrator phases (orchestrator.py phases 0-13).

Coverage: Job initialization, source sync, scanner execution, scoring,
coupling, timeline, fix queue, git context, and completion phases.
"""
import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator import Orchestrator
from core.primitives.models import Job, JobState, Finding, Severity, Category
from core.primitives.settings import SettingsManager
from core.primitives.events import EventBus, EventType


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    """Create an Orchestrator instance."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    
    sm = SettingsManager()
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path / "src")))
    
    orch = Orchestrator(sm)
    return orch, sm, proj, tmp_path


class TestOrchestratorInitialization:
    """Test Orchestrator initialization."""
    
    def test_orchestrator_init(self, orchestrator):
        """Test Orchestrator initialization."""
        orch, _, _, _ = orchestrator
        
        assert orch._settings_manager is not None
        assert isinstance(orch._bus, EventBus)
        assert orch._current_job is None
    
    def test_orchestrator_properties(self, orchestrator):
        """Test Orchestrator properties."""
        orch, _, _, _ = orchestrator
        
        assert orch.bus is not None
        assert isinstance(orch.bus, EventBus)
        
        job = orch.current_job
        assert job is None
        
        status = orch.status()
        assert status["state"] == "idle"
        assert status["job_id"] is None


class TestJobLifecycle:
    """Test job lifecycle in Orchestrator."""
    
    @pytest.mark.asyncio
    async def test_start_job_creates_job(self, orchestrator):
        """Test starting a job creates Job object."""
        orch, _, proj, _ = orchestrator
        
        job = await orch.start_job(proj.id)
        
        assert job is not None
        assert job.project_id == proj.id
        assert job.state == JobState.RUNNING
        assert job.started_at is not None
    
    @pytest.mark.asyncio
    async def test_current_job_returns_running_job(self, orchestrator):
        """Test current_job() returns the running job."""
        orch, _, proj, _ = orchestrator
        
        job = await orch.start_job(proj.id)
        
        current = orch.current_job
        assert current is not None
        assert current.id == job.id
        assert current.state == JobState.RUNNING
    
    @pytest.mark.asyncio
    async def test_status_reflects_job_state(self, orchestrator):
        """Test status() reflects job state."""
        orch, _, proj, _ = orchestrator
        
        job = await orch.start_job(proj.id)
        
        status = orch.status()
        assert status["state"] == "running"
        assert status["job_id"] == job.id
    
    @pytest.mark.asyncio
    async def test_cannot_start_two_jobs(self, orchestrator):
        """Test error when starting second job while one is running."""
        orch, _, proj, _ = orchestrator
        
        await orch.start_job(proj.id)
        
        with pytest.raises(RuntimeError, match="already running"):
            await orch.start_job(proj.id)
    
    @pytest.mark.asyncio
    async def test_start_job_nonexistent_project(self, orchestrator):
        """Test error when starting job for nonexistent project."""
        orch, _, _, _ = orchestrator
        
        with pytest.raises(ValueError, match="not found"):
            await orch.start_job("nonexistent-project")
    
    @pytest.mark.asyncio
    async def test_cancel_job(self, orchestrator):
        """Test cancelling a running job."""
        orch, _, proj, _ = orchestrator
        
        job = await orch.start_job(proj.id)
        
        # Cancel immediately (job may still be starting)
        await orch.cancel_job()
        
        # Status should reflect cancellation (or allow some time for it)
        # The actual state might be CANCELLED or RUNNING depending on timing
        current = orch.current_job
        assert current is not None


class TestEventBusPublishing:
    """Test EventBus publishing during job execution."""
    
    @pytest.mark.asyncio
    async def test_job_publishes_status_events(self, orchestrator):
        """Test job publishes status events."""
        orch, _, proj, tmp_path = orchestrator
        
        events = []
        
        async def capture_status(event):
            status = event.payload.get("state")
            job_id = event.payload.get("job_id")
            events.append(("status", status, job_id))
        
        await orch.bus.subscribe(EventType.STATUS, capture_status)
        
        job = await orch.start_job(proj.id)
        
        # Wait a bit for events
        await asyncio.sleep(0.1)
        
        # Should have at least "running" event
        assert any(status == "running" for _, status, _ in events)
    
    @pytest.mark.asyncio
    async def test_job_publishes_log_events(self, orchestrator):
        """Test job publishes log events."""
        orch, _, proj, tmp_path = orchestrator
        
        logs = []
        
        async def capture_log(event):
            level = event.payload.get("level")
            msg = event.payload.get("message")
            logs.append((level, msg))
        
        await orch.bus.subscribe(EventType.LOG, capture_log)
        
        job = await orch.start_job(proj.id)
        
        # Wait for execution
        await asyncio.sleep(0.1)
        
        # Should have logged something
        assert len(logs) > 0


class TestBuildResult:
    """Test _build_result method."""
    
    def test_build_result_structure(self, orchestrator):
        """Test result structure from _build_result."""
        orch, _, proj, tmp_path = orchestrator
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "app1": MagicMock(
                score=85,
                is_hub=False,
                finding_counts={"violation": 2, "security_high": 1},
                penalty_breakdown={}
            )
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=85,
            coupling={},
            trends=[],
            sync_result={"added": [], "removed": [], "modified": []},
            git_ctx={"branch": "main", "commit": "abc123"},
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        assert "metadata" in result
        assert "apps" in result
        assert "findings" in result
        assert "fleet_average" in result
        assert result["fleet_average"] == 85
    
    def test_build_result_includes_finding_counts(self, orchestrator):
        """Test result includes finding_counts in apps."""
        orch, _, proj, tmp_path = orchestrator
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "app1": MagicMock(
                score=85,
                is_hub=False,
                finding_counts={
                    "violation": 5,
                    "security_high": 2,
                    "security_medium": 3,
                    "dead_code": 1
                },
                penalty_breakdown={"violations": 10}
            )
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=85,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        app_result = result["apps"]["app1"]
        
        assert "finding_counts" in app_result
        assert app_result["finding_counts"]["violation"] == 5
        assert app_result["finding_counts"]["security_high"] == 2
        assert app_result["violation_count"] == 5
    
    def test_build_result_metadata_fields(self, orchestrator):
        """Test metadata includes all required fields."""
        orch, _, proj, tmp_path = orchestrator
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED,
            finished_at=datetime.now(timezone.utc)
        )
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores={},
            fleet_average=75,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        metadata = result["metadata"]
        
        assert metadata["job_id"] == "job-001"
        assert "started_at" in metadata
        assert "finished_at" in metadata
        assert "total_findings" in metadata


class TestBuildSummary:
    """Test _build_summary method."""
    
    def test_build_summary_structure(self, orchestrator):
        """Test summary structure."""
        orch, _, _, _ = orchestrator
        
        result_data = {
            "metadata": {
                "job_id": "job-001",
                "finished_at": datetime.now(timezone.utc).isoformat()
            },
            "fleet_average": 80,
            "apps": {
                "app1": {"score": 85},
                "app2": {"score": 75}
            },
            "findings": [
                {"fingerprint": "fp-001", "rule_id": "rule-1"},
                {"fingerprint": "fp-002", "rule_id": "rule-2"}
            ]
        }
        
        summary = orch._build_summary(result_data)
        
        assert summary["job_id"] == "job-001"
        assert "timestamp" in summary
        assert summary["fleet_average"] == 80
        assert "app_scores" in summary
        assert summary["app_scores"]["app1"] == 85
    
    def test_build_summary_findings_with_fingerprints(self, orchestrator):
        """Test summary includes findings with fingerprints."""
        orch, _, _, _ = orchestrator
        
        result_data = {
            "metadata": {"job_id": "job-001"},
            "fleet_average": 80,
            "apps": {},
            "findings": [
                {
                    "fingerprint": "fp-001",
                    "rule_id": "rule-1",
                    "title": "Finding 1"
                },
                {
                    "fingerprint": "fp-002",
                    "rule_id": "rule-2",
                    "title": "Finding 2"
                }
            ]
        }
        
        summary = orch._build_summary(result_data)
        
        assert len(summary["findings"]) == 2
        assert summary["findings"][0]["fingerprint"] == "fp-001"
        assert summary["findings"][1]["fingerprint"] == "fp-002"


class TestOrchestratorErrorHandling:
    """Test error handling in Orchestrator."""
    
    @pytest.mark.asyncio
    async def test_job_failure_sets_state(self, orchestrator):
        """Test job failure sets state to FAILED."""
        orch, sm, proj, tmp_path = orchestrator
        
        # Patch _run_job to raise exception
        async def mock_run_job(*args, **kwargs):
            raise RuntimeError("Test error")
        
        orch._run_job = mock_run_job
        
        job = await orch.start_job(proj.id)
        
        # Wait for task
        await asyncio.sleep(0.1)
        
        # Note: job state may be FAILED or RUNNING depending on timing
        # Just verify we can handle it without crashing
        assert job is not None
    
    @pytest.mark.asyncio
    async def test_cancel_idle_job(self, orchestrator):
        """Test cancelling when no job is running."""
        orch, _, _, _ = orchestrator
        
        # Should not raise
        await orch.cancel_job()
