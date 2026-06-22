import pytest
from unittest.mock import patch, MagicMock
from orchestrator import Orchestrator

@pytest.mark.asyncio
@patch("core.infra.audit_index.diff_runs")
@patch("core.infra.audit_index.get_trend")
async def test_diff_runs(mock_get_trend, mock_idx_diff_runs):
    mock_get_trend.return_value = [
        {"run_id": "runB", "score_overall": 90.0, "score_security": 80.0, "score_quality": 100.0, "timestamp": 100},
        {"run_id": "runA", "score_overall": 80.0, "score_security": 70.0, "score_quality": 90.0, "timestamp": 50}
    ]
    mock_idx_diff_runs.return_value = {
        "new": [{"severity": "HIGH"}, {"severity": "HIGH"}],
        "resolved": [{"severity": "LOW"}]
    }

    orchestrator = Orchestrator(MagicMock())
    
    # Passing None uses defaults (run_b = runB, run_a = runA)
    res = await orchestrator.diff_runs("proj1", None, None)
    
    assert res["run_id_a"] == "runA"
    assert res["run_id_b"] == "runB"
    assert res["score_delta"]["overall"] == 10.0
    assert res["score_delta"]["security"] == 10.0
    assert res["score_delta"]["quality"] == 10.0
    assert res["new_findings"]["count"] == 2
    assert res["new_findings"]["by_severity"]["HIGH"] == 2
    assert res["resolved_findings"]["count"] == 1

@pytest.mark.asyncio
@patch("core.infra.audit_index.get_trend")
async def test_get_trend(mock_idx_get_trend):
    mock_idx_get_trend.return_value = [
        {
            "run_id": "runB", "score_overall": 90.0, "score_security": 80.0, "score_quality": 100.0, 
            "timestamp": 1700000000, "CRITICAL_count": 0, "HIGH_count": 1
        },
        {
            "run_id": "runA", "score_overall": 80.0, "score_security": 70.0, "score_quality": 90.0, 
            "timestamp": 1600000000, "CRITICAL_count": 1, "HIGH_count": 2
        }
    ]
    
    orchestrator = Orchestrator(MagicMock())
    res = await orchestrator.get_trend("proj1", 10, None)
    
    # Should be returned in reverse order
    assert len(res["runs"]) == 2
    
    assert res["runs"][0]["scores"]["overall"] == 80.0
    assert res["runs"][1]["scores"]["overall"] == 90.0
    assert res["runs"][0]["counts"]["critical"] == 1
    assert res["runs"][1]["counts"]["critical"] == 0

@pytest.mark.asyncio
@patch("core.infra.audit_index.get_fix_queue")
async def test_get_fix_queue(mock_idx_get_fix_queue):
    mock_idx_get_fix_queue.return_value = [
        {"fingerprint": "f1", "category": "r1", "severity": "CRITICAL", "file_path": "f.py", "first_seen_ts": 0},
        {"fingerprint": "f2", "category": "r2", "severity": "MEDIUM", "file_path": "f.py", "first_seen_ts": 0},
        {"fingerprint": "f3", "category": "r3", "severity": "HIGH", "file_path": "f.py", "first_seen_ts": 0}
    ]
    
    orchestrator = Orchestrator(MagicMock())
    
    # Filter for HIGH and above
    res = await orchestrator.get_fix_queue("proj1", severity_floor="HIGH", limit=10)
    
    assert res["total"] == 2
    assert len(res["queue"]) == 2
    
    assert res["queue"][0]["severity"] == "CRITICAL"
    assert res["queue"][1]["severity"] == "HIGH"
    
@pytest.mark.asyncio
async def test_export_audit():
    orchestrator = Orchestrator(MagicMock())
    res = await orchestrator.export_audit("proj1", "sarif", 90, "out.sarif")
    assert res["findings_count"] == 0
    assert res["output_path"] == "out.sarif"
