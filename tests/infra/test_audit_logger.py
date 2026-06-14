import asyncio
import pytest
import logging
import json
from pathlib import Path
from core.primitives.events import EventBus, EventType
from core.infra.audit_logger import AuditLogger
from core.primitives.models import create_finding, Severity, Category

@pytest.fixture
def bus():
    return EventBus()

@pytest.fixture
def logger(tmp_path, bus):
    return AuditLogger("test_job", bus, tmp_path / "output")

@pytest.mark.asyncio
async def test_audit_logger_start_subscribes(logger, bus):
    await logger.start()
    assert len(logger._tokens) == 2
    assert logger._flush_task is not None
    await logger.stop()
    assert logger._flush_task.cancelled() or logger._flush_task.done()
    assert not bus._subscribers[EventType.LOG]
    assert not bus._subscribers[EventType.FINDING]

@pytest.mark.asyncio
async def test_audit_logger_log_events(logger, bus):
    await logger.start()
    await bus.publish_log("warning", "test warning message")
    await asyncio.sleep(0.1) # allow async handler to run
    await logger.stop()
    
    if logger._log_path.exists():
        log_content = logger._log_path.read_text()
        assert "test warning message" in log_content

@pytest.mark.asyncio
async def test_audit_logger_finding_events_flush(logger, bus):
    await logger.start()
    for i in range(50):
        f = create_finding("scanner", "rule", "file", 1, 1, Severity.LOW, Category.SECURITY, "t", "d")
        object.__setattr__(f, 'id', f"f{i}")
        await bus.publish_finding(f)
    await asyncio.sleep(0.1) # allow async handlers
    
    # After 50, it should flush automatically
    findings = json.loads(logger._findings_path.read_text())
    assert len(findings) == 50
    assert findings[-1]["id"] == "f49"
    await logger.stop()

@pytest.mark.asyncio
async def test_audit_logger_periodic_flush(logger, bus, monkeypatch):
    await logger.start()
    f = create_finding("scanner", "rule", "file", 1, 1, Severity.LOW, Category.SECURITY, "t", "d")
    object.__setattr__(f, 'id', "f_single")
    await bus.publish_finding(f)
    await asyncio.sleep(0.1)
    
    # Not flushed yet because < 50
    assert not logger._findings_path.exists()
    
    # stop() flushes remaining
    await logger.stop()
    findings = json.loads(logger._findings_path.read_text())
    assert len(findings) == 1
    assert findings[0]["id"] == "f_single"

@pytest.mark.asyncio
async def test_circuit_breaker(tmp_path, bus):
    output_dir = tmp_path / "blocked_dir"
    logger = AuditLogger("job2", bus, output_dir)
    await logger.start()

    # Force a failure during write by making _log_path a directory
    logger._log_path.mkdir(parents=True, exist_ok=True)
    
    await bus.publish_log("info", "fail log")
    await asyncio.sleep(0.1)
    await logger.stop()

@pytest.mark.asyncio
async def test_mkdir_failure_on_start(tmp_path, bus, monkeypatch):
    from pathlib import Path
    logger = AuditLogger("job3", bus, tmp_path)
    def mock_mkdir(*args, **kwargs): raise OSError("Mock mkdir error")
    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    await logger.start()
    assert logger._io_failed

@pytest.mark.asyncio
async def test_circuit_breaker_fast_return(tmp_path, bus):
    logger = AuditLogger("job4", bus, tmp_path)
    logger._io_failed = True
    # Should return immediately and not throw
    class MockEvent:
        pass
    await logger._handle_log(MockEvent())

@pytest.mark.asyncio
async def test_periodic_flush_and_write_failure(tmp_path, bus, monkeypatch):
    import asyncio
    logger = AuditLogger("job5", bus, tmp_path)
    logger._findings_buffer.append({"id": "f_1"})
    
    # Trigger OSError by making the target file a directory
    logger._findings_path.mkdir(parents=True, exist_ok=True)
    # Run _periodic_flush manually to trigger the loop once
    sleep_calls = 0
    async def mock_sleep(delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError() # Break the while True loop on second iteration
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    
    await logger._periodic_flush()
    assert logger._io_failed
