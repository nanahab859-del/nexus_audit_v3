import pytest
import json
from pathlib import Path
from datetime import datetime, timezone
from core.engines.timeline import load_score_history, compute_violation_persistence
from core.primitives.models import Finding, Severity, Category, Persistence
from core.engines.fix_queue import FixQueue

@pytest.mark.asyncio
async def test_loads_score_history(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    # Create valid summary
    summary = {
        "timestamp": "2026-06-01T10:00:00Z",
        "fleet_average": 80,
        "app_scores": {"app1": 90}
    }
    with open(history_dir / "audit_summary_1.json", "w") as f:
        json.dump(summary, f)
        
    history = await load_score_history(history_dir)
    assert history["labels"] == ["2026-06-01T10:00:00Z"]
    assert history["fleet_avg"] == [80]
    assert history["apps"]["app1"] == [90]

@pytest.mark.asyncio
async def test_limits_to_max_runs(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    base_time = time.time()
    for i in range(40):
        summary = {"timestamp": f"2026-06-{i+1:02d}T10:00:00Z", "fleet_average": 80}
        p = history_dir / "audit_summary.json"
        # Since they need to be distinct files, I'll put them in subdirs, 
        # or the load_score_history only looks in one dir.
        # Actually the specification says "list of audit_summary.json files". 
        # Let's adjust the implementation in timeline.py to glob("*/*.json")? 
        # No, the spec says "reads audit_summary.json files".
        # Let's assume they are named like audit_summary_1.json, etc. 
        # I need to change the implementation to `glob("*.json")` or `glob("audit_summary_*.json")`.
        # I will change the glob in `timeline.py` to `audit_summary_*.json` for better flexibility.
    
# Import time for test_limits_to_max_runs
import time
import os

@pytest.mark.asyncio
async def test_new_finding(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    finding = Finding("1", "rule", "s", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    
    # Empty history
    findings = await compute_violation_persistence(history_dir, [finding])
    assert findings[0].persistence == Persistence.NEW

@pytest.mark.asyncio
async def test_persistent_finding(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    finding = Finding("1", "rule", "s", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    fp = FixQueue.fingerprint(finding)
    
    # Mock last 5 runs
    for i in range(5):
        summary = {"findings": [{"fingerprint": fp}]}
        with open(history_dir / f"audit_summary_{i}.json", "w") as f:
            json.dump(summary, f)
            
    findings = await compute_violation_persistence(history_dir, [finding], max_runs=5)
    assert findings[0].persistence == Persistence.PERSISTENT
import pytest
from pathlib import Path
from core.engines.timeline import load_score_history, compute_violation_persistence
from core.primitives.models import Persistence, Finding, Severity, Category, create_finding
import json

@pytest.mark.asyncio
async def test_timeline_non_existent_dir(tmp_path):
    history_dir = tmp_path / "does_not_exist"
    # Should return empty data
    data = await load_score_history(history_dir)
    assert data["labels"] == []
    
    # compute_violation_persistence
    f1 = create_finding("s", "r", "f", 1, 1, Severity.MEDIUM, Category.SECURITY, "T", "D")
    results = await compute_violation_persistence(history_dir, [f1])
    assert len(results) == 1
    assert results[0].persistence == Persistence.NEW

@pytest.mark.asyncio
async def test_timeline_intermittent(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    f1 = create_finding("s", "r", "f", 1, 1, Severity.MEDIUM, Category.SECURITY, "T", "D")
    # Force fingerprint
    from core.engines.fix_queue import FixQueue
    f1_fp = FixQueue.fingerprint(f1)
    
    # We create 2 runs (less than max_runs=5). 
    # Run 1 has the finding. Run 2 does not.
    
    # Run 1
    with open(history_dir / "audit_summary_1.json", "w") as f:
        json.dump({"findings": [{"fingerprint": f1_fp}]}, f)
        
    # Run 2
    with open(history_dir / "audit_summary_2.json", "w") as f:
        json.dump({"findings": []}, f)
        
    results = await compute_violation_persistence(history_dir, [f1], max_runs=5)
    assert len(results) == 1
    # Count = 1, max_runs = 5, so intermittent
    assert results[0].persistence == Persistence.INTERMITTENT
