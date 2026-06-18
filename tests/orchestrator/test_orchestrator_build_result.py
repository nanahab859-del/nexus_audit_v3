"""
Tests for orchestrator _build_result and _build_summary methods.

Coverage: Result data structure, finding counts, app scores, metadata,
summary generation, and edge cases.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from pathlib import Path

from orchestrator import Orchestrator
from core.primitives.models import Job, JobState, Finding, Severity, Category
from core.primitives.settings import SettingsManager


@pytest.fixture
def orchestrator_with_settings(tmp_path, monkeypatch):
    """Create Orchestrator with settings manager."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    
    sm = SettingsManager()
    import asyncio
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path / "src")))
    
    orch = Orchestrator(sm)
    return orch, sm, proj, tmp_path


class TestBuildResultAppsDict:
    """Test apps dictionary construction in _build_result."""
    
    def test_result_app_score_fields(self, orchestrator_with_settings):
        """Test apps dict includes all score fields."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "service-a": MagicMock(
                score=87,
                is_hub=True,
                finding_counts={
                    "violation": 3,
                    "security_high": 1,
                    "security_medium": 2,
                    "security_low": 0,
                    "dead_code": 5,
                    "ghost_file": 1,
                    "complexity": 2.5
                },
                penalty_breakdown={
                    "violations": 15,
                    "security_penalties": 5,
                    "complexity_penalties": 10
                }
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
        
        app = result["apps"]["service-a"]
        
        assert app["score"] == 87
        assert app["is_hub"] == True
        assert app["finding_counts"]["violation"] == 3
        assert app["security_high"] == 1
        assert app["security_medium"] == 2
        assert app["dead_code_count"] == 5
        assert app["ghost_file_count"] == 1
        assert app["avg_complexity"] == 2.5
        assert app["penalty_breakdown"]["violations"] == 15
    
    def test_result_app_finding_count_calculation(self, orchestrator_with_settings):
        """Test finding_count is sum of all counts."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "app1": MagicMock(
                score=80,
                is_hub=False,
                finding_counts={
                    "violation": 2,
                    "security_high": 1,
                    "security_medium": 3,
                    "dead_code": 4
                },
                penalty_breakdown={}
            )
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=80,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        app = result["apps"]["app1"]
        
        # finding_count should be sum: 2+1+3+4 = 10
        assert app["finding_count"] == 10
        assert app["violation_count"] == 2
    
    def test_result_multiple_apps(self, orchestrator_with_settings):
        """Test result with multiple apps."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "frontend": MagicMock(score=90, is_hub=True, finding_counts={}, penalty_breakdown={}),
            "backend": MagicMock(score=75, is_hub=False, finding_counts={}, penalty_breakdown={}),
            "utils": MagicMock(score=95, is_hub=False, finding_counts={}, penalty_breakdown={})
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=87,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        assert len(result["apps"]) == 3
        assert result["apps"]["frontend"]["score"] == 90
        assert result["apps"]["backend"]["score"] == 75
        assert result["apps"]["utils"]["score"] == 95
    
    def test_result_total_violations_calculation(self, orchestrator_with_settings):
        """Test total_violations in metadata."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            "app1": MagicMock(score=80, is_hub=False, finding_counts={"violation": 5}, penalty_breakdown={}),
            "app2": MagicMock(score=75, is_hub=False, finding_counts={"violation": 3}, penalty_breakdown={}),
            "app3": MagicMock(score=70, is_hub=False, finding_counts={"violation": 2}, penalty_breakdown={})
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=75,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        # Total violations: 5 + 3 + 2 = 10
        assert result["metadata"]["total_violations"] == 10


class TestBuildResultMetadata:
    """Test metadata section of _build_result."""
    
    def test_metadata_required_fields(self, orchestrator_with_settings):
        """Test metadata has all required fields."""
        orch, _, proj, _ = orchestrator_with_settings
        
        start_time = datetime.now(timezone.utc)
        job = Job(
            id="job-123",
            project_id=proj.id,
            project_path=proj.path,
            started_at=start_time,
            state=JobState.COMPLETED
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
        
        assert metadata["job_id"] == "job-123"
        assert metadata["project_path"] == proj.path
        assert "started_at" in metadata
        assert "finished_at" in metadata
        assert "total_findings" in metadata
        assert "total_violations" in metadata
    
    def test_metadata_git_context_included(self, orchestrator_with_settings):
        """Test git_context is included in metadata."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        git_ctx = {
            "branch": "feature/new",
            "commit": "abc123def456",
            "author": "developer",
            "dirty": False
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores={},
            fleet_average=75,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=git_ctx,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        assert result["metadata"]["git_context"] == git_ctx
    
    def test_metadata_total_findings_count(self, orchestrator_with_settings):
        """Test total_findings is correct."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        findings = [
            MagicMock(file="app1/file.py", line=1),
            MagicMock(file="app1/file.py", line=2),
            MagicMock(file="app2/file.py", line=1),
        ]
        
        result = orch._build_result(
            job=job,
            all_findings=findings,
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
        
        assert result["metadata"]["total_findings"] == 3


class TestBuildResultFindings:
    """Test findings in _build_result."""
    
    def test_findings_included_with_fingerprint(self, orchestrator_with_settings):
        """Test findings are included with fingerprints."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        # Mock findings
        finding1 = MagicMock()
        finding1.to_dict = MagicMock(return_value={"title": "Finding 1", "rule_id": "R1"})
        
        finding2 = MagicMock()
        finding2.to_dict = MagicMock(return_value={"title": "Finding 2", "rule_id": "R2"})
        
        result = orch._build_result(
            job=job,
            all_findings=[finding1, finding2],
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
        
        assert len(result["findings"]) == 2
        assert "fingerprint" in result["findings"][0]


class TestBuildSummaryFields:
    """Test _build_summary method fields."""
    
    def test_summary_required_fields(self, orchestrator_with_settings):
        """Test summary has all required fields."""
        orch, _, _, _ = orchestrator_with_settings
        
        result_data = {
            "metadata": {
                "job_id": "job-123",
                "finished_at": "2024-01-15T10:30:00+00:00"
            },
            "fleet_average": 82,
            "apps": {
                "app1": {"score": 85},
                "app2": {"score": 79}
            },
            "findings": [
                {"fingerprint": "fp1", "rule_id": "R1"},
                {"fingerprint": "fp2", "rule_id": "R2"}
            ]
        }
        
        summary = orch._build_summary(result_data)
        
        assert "job_id" in summary
        assert "timestamp" in summary
        assert "fleet_average" in summary
        assert "app_scores" in summary
        assert "findings_count" in summary
        assert "findings" in summary
    
    def test_summary_app_scores_extraction(self, orchestrator_with_settings):
        """Test app_scores are correctly extracted."""
        orch, _, _, _ = orchestrator_with_settings
        
        result_data = {
            "metadata": {"job_id": "job-1"},
            "fleet_average": 75,
            "apps": {
                "frontend": {"score": 88, "other": "data"},
                "backend": {"score": 72, "other": "data"},
                "api": {"score": 85, "other": "data"}
            },
            "findings": []
        }
        
        summary = orch._build_summary(result_data)
        
        app_scores = summary["app_scores"]
        assert app_scores["frontend"] == 88
        assert app_scores["backend"] == 72
        assert app_scores["api"] == 85
    
    def test_summary_findings_count(self, orchestrator_with_settings):
        """Test findings_count is correct."""
        orch, _, _, _ = orchestrator_with_settings
        
        result_data = {
            "metadata": {"job_id": "job-1"},
            "fleet_average": 75,
            "apps": {},
            "findings": [
                {"fingerprint": "fp1", "rule_id": "R1"},
                {"fingerprint": "fp2", "rule_id": "R2"},
                {"fingerprint": "fp3", "rule_id": "R3"}
            ]
        }
        
        summary = orch._build_summary(result_data)
        
        assert summary["findings_count"] == 3
    
    def test_summary_timestamp_from_result(self, orchestrator_with_settings):
        """Test timestamp is taken from result."""
        orch, _, _, _ = orchestrator_with_settings
        
        timestamp = "2024-06-15T14:30:00+00:00"
        result_data = {
            "metadata": {
                "job_id": "job-1",
                "finished_at": timestamp
            },
            "fleet_average": 75,
            "apps": {},
            "findings": []
        }
        
        summary = orch._build_summary(result_data)
        
        assert summary["timestamp"] == timestamp
    
    def test_summary_findings_filtering(self, orchestrator_with_settings):
        """Test only findings with fingerprint are included."""
        orch, _, _, _ = orchestrator_with_settings
        
        result_data = {
            "metadata": {"job_id": "job-1"},
            "fleet_average": 75,
            "apps": {},
            "findings": [
                {"fingerprint": "fp1", "rule_id": "R1", "title": "Finding 1"},
                {"fingerprint": None, "rule_id": "R2", "title": "Finding 2"},  # No fingerprint
                {"rule_id": "R3", "title": "Finding 3"},  # Missing fingerprint key
                {"fingerprint": "fp4", "rule_id": "R4", "title": "Finding 4"}
            ]
        }
        
        summary = orch._build_summary(result_data)
        
        # Only findings with fingerprint should be included
        assert len(summary["findings"]) == 2
        assert summary["findings"][0]["fingerprint"] == "fp1"
        assert summary["findings"][1]["fingerprint"] == "fp4"


class TestBuildResultEdgeCases:
    """Test edge cases in _build_result."""
    
    def test_result_empty_apps(self, orchestrator_with_settings):
        """Test result with no apps."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores={},
            fleet_average=0,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        assert result["apps"] == {}
        assert result["fleet_average"] == 0
    
    def test_result_no_git_context(self, orchestrator_with_settings):
        """Test result when git_context is None."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores={},
            fleet_average=50,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        assert result["metadata"]["git_context"] is None
        assert result["git_context"] is None
    
    def test_result_high_violation_counts(self, orchestrator_with_settings):
        """Test result with high violation counts."""
        orch, _, proj, _ = orchestrator_with_settings
        
        job = Job(
            id="job-001",
            project_id=proj.id,
            project_path=proj.path,
            started_at=datetime.now(timezone.utc),
            state=JobState.COMPLETED
        )
        
        app_scores = {
            f"app{i}": MagicMock(
                score=50-i*5,
                is_hub=i==0,
                finding_counts={"violation": 50-i*5},
                penalty_breakdown={}
            )
            for i in range(10)
        }
        
        result = orch._build_result(
            job=job,
            all_findings=[],
            app_scores=app_scores,
            fleet_average=25,
            coupling={},
            trends=[],
            sync_result={},
            git_ctx=None,
            recommendations=[],
            rules_engine=MagicMock(app_definitions=[], scoring_config={}),
            dna=MagicMock()
        )
        
        # Verify total_violations is calculated correctly
        expected_total = sum(50-i*5 for i in range(10))
        assert result["metadata"]["total_violations"] == expected_total
