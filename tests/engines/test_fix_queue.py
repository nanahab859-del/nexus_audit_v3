import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from core.engines.fix_queue import FixQueue
from core.primitives.models import Finding, Severity, Category, create_finding

@pytest.mark.asyncio
async def test_fingerprint_deterministic(tmp_path):
    f1 = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    f2 = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    
    assert FixQueue.fingerprint(f1) == FixQueue.fingerprint(f2)

@pytest.mark.asyncio
async def test_fingerprint_ignores_line(tmp_path):
    f1 = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D", snippet="code")
    f2 = create_finding("s", "r", "f", 100, 1, Severity.INFO, Category.QUALITY, "T", "D", snippet="code")
    
    assert FixQueue.fingerprint(f1) == FixQueue.fingerprint(f2)

@pytest.mark.asyncio
async def test_sync_new_findings(tmp_path):
    queue_path = tmp_path / "queue.json"
    fq = FixQueue(queue_path)
    f = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    
    res = await fq.sync([f])
    assert res.new_count == 1
    assert await fq.get_status(FixQueue.fingerprint(f)) == "open"

@pytest.mark.asyncio
async def test_sync_reappeared(tmp_path):
    queue_path = tmp_path / "queue.json"
    fq = FixQueue(queue_path)
    f = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    fp = FixQueue.fingerprint(f)
    
    await fq.update_status(fp, "done")
    
    res = await fq.sync([f])
    assert len(res.reappeared) == 1
    assert await fq.get_status(fp) == "open"

@pytest.mark.asyncio
async def test_sync_resolved(tmp_path):
    queue_path = tmp_path / "queue.json"
    fq = FixQueue(queue_path)
    f = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    fp = FixQueue.fingerprint(f)
    
    await fq.update_status(fp, "done")
    
    res = await fq.sync([])
    assert res.resolved_count == 1
    # Check if entry is still in data for the 30-day window
    assert await fq.get_status(fp) == "done"

@pytest.mark.asyncio
async def test_pruning(tmp_path):
    queue_path = tmp_path / "queue.json"
    fq = FixQueue(queue_path)
    f = create_finding("s", "r", "f", 1, 1, Severity.INFO, Category.QUALITY, "T", "D")
    fp = FixQueue.fingerprint(f)
    
    # Manually set to done 31 days ago
    await fq.update_status(fp, "done")
    fq._data[fp]["updated_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    await fq._save()
    
    res = await fq.sync([])
    assert await fq.get_status(fp) is None
import pytest
from pathlib import Path
from core.engines.fix_queue import FixQueue, SyncResult
from core.primitives.models import Finding, FixStatus, Severity, Category, create_finding

@pytest.mark.asyncio
async def test_fix_queue_corrupt_json(tmp_path):
    q_path = tmp_path / "q.json"
    q_path.write_text("{invalid json")
    
    fq = FixQueue(q_path)
    # This should hit the exception block in _load and reset data to {}
    await fq._load()
    assert fq._data == {}

@pytest.mark.asyncio
async def test_update_status_with_note(tmp_path):
    q_path = tmp_path / "q.json"
    fq = FixQueue(q_path)
    
    await fq.update_status("fp123", FixStatus.DONE.value, note="Fixed manually")
    assert fq._data["fp123"]["note"] == "Fixed manually"

@pytest.mark.asyncio
async def test_sync_persistent_finding(tmp_path):
    q_path = tmp_path / "q.json"
    fq = FixQueue(q_path)
    
    f1 = create_finding("s", "r", "f", 1, 1, Severity.MEDIUM, Category.SECURITY, "T", "D")
    
    # Sync first time (new finding)
    res1 = await fq.sync([f1])
    assert res1.new_count == 1
    
    # Sync second time (persistent finding)
    res2 = await fq.sync([f1])
    assert res2.persistent_count == 1
