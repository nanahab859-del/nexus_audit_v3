import pytest
import sqlite3
import asyncio
import json
from pathlib import Path
from core.infra.audit_index import open_index, upsert_run, rebuild_index

@pytest.fixture
def project_id():
    return "test-project-123"

@pytest.mark.asyncio
async def test_schema_creates_tables(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cursor.fetchall()}
    assert "runs" in tables
    assert "findings" in tables
    conn.close()

@pytest.mark.asyncio
async def test_wal_pragma_active(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()

@pytest.mark.asyncio
async def test_upsert_run_inserts_row(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    job_dir = tmp_path / "jobs" / "job1"
    summary = {
        "job_id": "job1",
        "timestamp": "2023-10-01T12:00:00Z",
        "fleet_average": 95.5,
        "app_scores": {"app1": 95.5},
        "findings_count": 1,
        "findings": [{"fingerprint": "fp1", "rule_id": "rule1"}]
    }
    await upsert_run(project_id, summary, job_dir)
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs WHERE job_id='job1'")
    row = cursor.fetchone()
    assert row is not None
    assert row["job_id"] == "job1"
    assert row["fleet_average"] == 95.5
    conn.close()

@pytest.mark.asyncio
async def test_upsert_run_idempotent(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    job_dir = tmp_path / "jobs" / "job1"
    summary = {
        "job_id": "job1",
        "timestamp": "2023-10-01T12:00:00Z",
        "fleet_average": 95.5,
        "findings_count": 0
    }
    await upsert_run(project_id, summary, job_dir)
    await upsert_run(project_id, summary, job_dir)
    
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs WHERE job_id='job1'")
    count = cursor.fetchone()[0]
    assert count == 1
    conn.close()

@pytest.mark.asyncio
async def test_rebuild_index_produces_rows(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / project_id / "jobs"
    for i in range(3):
        job_dir = jobs_dir / f"job{i}"
        job_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "job_id": f"job{i}",
            "timestamp": "2023-10-01T12:00:00Z",
            "fleet_average": 100.0,
            "findings_count": 0
        }
        with open(job_dir / "audit_summary.json", "w") as f:
            json.dump(summary, f)
            
    res = await rebuild_index(project_id)
    assert res["runs_indexed"] == 3
    
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    assert cursor.fetchone()[0] == 3
    conn.close()

@pytest.mark.asyncio
async def test_rebuild_index_idempotent(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    jobs_dir = tmp_path / ".nexus_audit" / "projects" / project_id / "jobs"
    job_dir = jobs_dir / "job1"
    job_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "job_id": "job1",
        "timestamp": "2023-10-01T12:00:00Z"
    }
    with open(job_dir / "audit_summary.json", "w") as f:
        json.dump(summary, f)
        
    await rebuild_index(project_id)
    res2 = await rebuild_index(project_id)
    assert res2["runs_indexed"] == 1
    
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    assert cursor.fetchone()[0] == 1
    conn.close()

@pytest.mark.asyncio
async def test_findings_table_contains_one_row_per_fingerprint(project_id, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    job_dir = tmp_path / "jobs" / "job1"
    summary = {
        "job_id": "job1",
        "findings": [
            {"fingerprint": "fp1", "rule_id": "r1"},
            {"fingerprint": "fp2", "rule_id": "r2"}
        ]
    }
    await upsert_run(project_id, summary, job_dir)
    conn = await open_index(project_id)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM findings WHERE run_id='job1'")
    assert cursor.fetchone()[0] == 2
    
    await upsert_run(project_id, summary, job_dir)
    cursor.execute("SELECT COUNT(*) FROM findings WHERE run_id='job1'")
    assert cursor.fetchone()[0] == 2
    conn.close()
