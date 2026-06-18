"""
Fixtures for report layer tests.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, timezone


@pytest.fixture
def tmp_projects_dir(tmp_path):
    """Create a temporary projects directory structure."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    return projects_dir


@pytest.fixture
def sample_result_data():
    """Sample audit result data matching audit_data_complete.json structure."""
    return {
        "metadata": {
            "job_id": "test-job-001",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
        "apps": {
            "app1": {
                "score": 85,
                "is_hub": False,
                "lines_of_code": 10000,
                "finding_counts": {
                    "architecture": 2,
                    "security": 3,
                    "quality": 5,
                    "complexity": 1,
                    "dead_code": 2,
                    "ghost_file": 0,
                },
                "penalty_breakdown": {
                    "violation": 2.5,
                    "security": 3.0,
                    "complexity": 1.5,
                    "dead_code": 2.0,
                    "ghost_file": 0.0,
                },
            },
            "app2": {
                "score": 72,
                "is_hub": True,
                "lines_of_code": 5000,
                "finding_counts": {
                    "architecture": 5,
                    "security": 8,
                    "quality": 3,
                    "complexity": 2,
                    "dead_code": 1,
                    "ghost_file": 1,
                },
                "penalty_breakdown": {
                    "violation": 5.0,
                    "security": 8.0,
                    "complexity": 2.0,
                    "dead_code": 1.0,
                    "ghost_file": 1.0,
                },
            },
        },
        "findings": [
            {
                "scanner": "bandit",
                "rule_id": "B101",
                "file": "app1/utils.py",
                "line": 42,
                "column": 8,
                "severity": "HIGH",
                "category": "SECURITY",
                "title": "Use of assert detected",
                "description": "Use of assert statement may be optimized away",
                "suggestion": "Use proper exception handling",
                "cwe": "CWE-390",
            },
            {
                "scanner": "pylint",
                "rule_id": "W0612",
                "file": "app1/models.py",
                "line": 15,
                "column": 0,
                "severity": "MEDIUM",
                "category": "QUALITY",
                "title": "Unused variable",
                "description": "Unused variable 'x'",
                "suggestion": "Remove unused variable or use it",
                "cwe": None,
            },
            {
                "scanner": "mypy",
                "rule_id": "error",
                "file": "app2/handlers.py",
                "line": 88,
                "column": 12,
                "severity": "CRITICAL",
                "category": "ARCHITECTURE",
                "title": "Type error",
                "description": "Incompatible types in assignment",
                "suggestion": "Add proper type hints",
                "cwe": None,
            },
        ],
        "git_context": {
            "commit": "a1b2c3d4e5f6789012345678901234567890abcd",
            "branch": "main",
            "author": "test@example.com",
        },
        "fleet_average": 78,
        "coupling": {},
        "trends": [],
    }


@pytest.fixture
def completed_job_dir(tmp_projects_dir, sample_result_data):
    """Create a completed job directory with audit_data_complete.json."""
    project_id = "project-001"
    job_id = "job-001"
    
    jobs_dir = tmp_projects_dir / project_id / "jobs" / job_id
    jobs_dir.mkdir(parents=True)
    
    # Write audit_data_complete.json
    data_file = jobs_dir / "audit_data_complete.json"
    data_file.write_text(json.dumps(sample_result_data, indent=2, default=str))
    
    return jobs_dir, sample_result_data


@pytest.fixture
def multiple_jobs_dir(tmp_projects_dir, sample_result_data):
    """Create multiple job directories for testing job selection."""
    project_id = "project-001"
    jobs_by_id = {}
    
    for i in range(3):
        job_id = f"job-{i:03d}"
        jobs_dir = tmp_projects_dir / project_id / "jobs" / job_id
        jobs_dir.mkdir(parents=True)
        
        data = sample_result_data.copy()
        data["metadata"]["job_id"] = job_id
        
        data_file = jobs_dir / "audit_data_complete.json"
        data_file.write_text(json.dumps(data, indent=2, default=str))
        
        jobs_by_id[job_id] = jobs_dir
    
    return tmp_projects_dir / project_id / "jobs", jobs_by_id


@pytest.fixture
def empty_projects_dir(tmp_path):
    """Create an empty projects directory (no jobs)."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    project_id = "project-no-jobs"
    project_dir = projects_dir / project_id
    project_dir.mkdir()
    return projects_dir, project_id
