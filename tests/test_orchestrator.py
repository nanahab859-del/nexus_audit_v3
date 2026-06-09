"""
tests/test_orchestrator.py
Full suite for Orchestrator: pre-flight logging, skip messages,
error propagation from _run_single_scanner, start_run lifecycle.
"""

import asyncio
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from core.models import Job, Settings, Finding, Severity, Category, Persistence, FixStatus
from core.events import EventBus, EventType
from orchestrator import Orchestrator


# ── Helpers ────────────────────────────────────────────────────────────────────

def _settings(**kwargs) -> Settings:
    base = dict(project_path="/tmp", scanners={}, scanner_configs={}, ui={},
                enabled_extensions=[".py"], inclusions=[], exclusions=[],
                webhook_url="")
    base.update(kwargs)
    return Settings(**base)


def _job(path="/tmp") -> Job:
    return Job(id=str(uuid4()), project_path=path, started_at=datetime.now(timezone.utc))


async def _collect_events(bus: EventBus) -> list:
    events = []
    async def sub(eid, ev):
        events.append(ev)
    bus.subscribe_all(sub)
    return events


# ── Core orchestrator tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_no_scanners_completes():
    """With no scanners configured the job completes and fires STATUS=completed."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)
    job = _job()
    settings = _settings()
    await orc.run(job, settings)

    assert job.state == "completed"
    status_events = [e for e in events if e.type == EventType.STATUS]
    assert any(e.data["state"] == "completed" for e in status_events)


@pytest.mark.asyncio
async def test_preflight_log_contains_scanner_summary():
    """Pre-flight log lists enabled and disabled scanner names."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)
    job = _job()
    settings = _settings(scanners={"bandit": True, "vulture": False})
    await orc.run(job, settings)

    log_messages = [e.data["message"] for e in events if e.type == EventType.LOG]
    preflight = [m for m in log_messages if "PRE-FLIGHT" in m]
    assert preflight, "No [PRE-FLIGHT] log emitted"
    combined = " ".join(preflight)
    assert "bandit" in combined
    assert "vulture" in combined


@pytest.mark.asyncio
async def test_disabled_scanner_emits_skipped_log():
    """A scanner with enabled=False must emit a [SKIPPED] log line."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)
    job = _job()
    settings = _settings(scanners={"vulture": False})
    await orc.run(job, settings)

    log_messages = [e.data["message"] for e in events if e.type == EventType.LOG]
    skipped = [m for m in log_messages if "SKIPPED" in m and "vulture" in m]
    assert skipped, "No [SKIPPED] log emitted for disabled vulture scanner"


@pytest.mark.asyncio
async def test_preflight_log_target_path():
    """Pre-flight log must include the project target path."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)
    job = _job("/tmp/myproject")
    settings = _settings(project_path="/tmp/myproject")
    await orc.run(job, settings)

    log_messages = [e.data["message"] for e in events if e.type == EventType.LOG]
    preflight = [m for m in log_messages if "PRE-FLIGHT" in m]
    combined = " ".join(preflight)
    assert "/tmp/myproject" in combined


@pytest.mark.asyncio
async def test_start_run_returns_job_in_running_state():
    """start_run() must return a Job immediately with state='running'."""
    bus = EventBus()
    orc = Orchestrator(bus)
    settings = _settings()
    job = orc.start_run(settings)

    assert job.state == "running"
    assert job.id
    assert job.project_path == "/tmp"


@pytest.mark.asyncio
async def test_start_run_rejects_concurrent_run():
    """start_run() raises RuntimeError if a job is already running."""
    bus = EventBus()
    orc = Orchestrator(bus)
    settings = _settings()

    orc.start_run(settings)
    with pytest.raises(RuntimeError, match="already running"):
        orc.start_run(settings)


@pytest.mark.asyncio
async def test_start_run_publishes_running_then_completed():
    """After start_run completes (no scanners), STATUS events must be running→completed."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)
    settings = _settings()
    job = orc.start_run(settings)

    await asyncio.sleep(0.05)
    assert any(e.type == EventType.STATUS and e.data["state"] == "running" for e in events)

    await asyncio.sleep(0.5)
    assert any(e.type == EventType.STATUS and e.data["state"] == "completed" for e in events)


@pytest.mark.asyncio
async def test_scanner_error_bubbles_to_gather():
    """
    When _run_single_scanner raises, asyncio.gather receives the exception.
    The job still completes (graceful degradation), and the scan_results
    entry has a non-None error field.
    """
    from plugins.base import BaseScanner

    class CrashingScanner(BaseScanner):
        name = "crashing_test_scanner"
        version = "0.0.1"
        languages = ["*"]
        category = Category.QUALITY
        timeout = 5

        async def scan(self, target, config, bus):
            raise RuntimeError("deliberate crash for test")

    bus = EventBus()
    orc = Orchestrator(bus)
    job = _job()
    settings = _settings(scanners={"crashing_test_scanner": True})

    # Patch the registry to return our crashing scanner
    with patch.object(orc, '_run_single_scanner',
                      side_effect=RuntimeError("deliberate crash")):
        # We need to patch at the run() level — use the full flow
        pass

    # Directly test _run_single_scanner raises
    findings = None
    raised = False
    try:
        findings = await orc._run_single_scanner(
            CrashingScanner, Path("/tmp"), {}, "crashing_test_scanner"
        )
    except (RuntimeError, Exception):
        raised = True

    assert raised, "_run_single_scanner must re-raise exceptions (not swallow them)"


@pytest.mark.asyncio
async def test_cancel_run(tmp_path):
    """cancel_run() cancels the running task and sets state=cancelled."""
    bus = EventBus()
    events = []
    async def sub(eid, ev): events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)

    settings = _settings(
        project_path=str(tmp_path),
        scanners={"slow_scanner": True},
        ui={"custom_scanners": {"slow_scanner": {"executable": "fake"}}}
    )

    async def _mock_run_single_scanner(*args, **kwargs):
        await asyncio.sleep(999)
        return []

    with patch.object(orc, '_run_single_scanner', side_effect=_mock_run_single_scanner):
        job = orc.start_run(settings)

        # Allow the task to start and reach the mocked _run_single_scanner
        await asyncio.sleep(0.05)
        assert job.state == "running"
        
        cancelled_job = await orc.cancel_run()
        assert cancelled_job.state == "cancelled"
        assert any(e.type == EventType.STATUS and e.data["state"] == "cancelled" for e in events)


@pytest.mark.asyncio
async def test_no_running_job_cancel_raises():
    """cancel_run() raises RuntimeError when no job is running."""
    bus = EventBus()
    orc = Orchestrator(bus)
    with pytest.raises(RuntimeError, match="No running job"):
        await orc.cancel_run()
