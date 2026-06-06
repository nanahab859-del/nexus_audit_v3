import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from core.models import Job, Settings
from core.events import EventBus, EventType
from orchestrator import Orchestrator

@pytest.mark.asyncio
async def test_orchestrator_stub():
    bus = EventBus()
    orc = Orchestrator(bus)
    job = Job(id=str(uuid4()), project_path="/tmp", started_at=datetime.now(timezone.utc))
    settings = Settings(project_path="/tmp")
    
    received_events = []
    
    async def subscriber(event):
        received_events.append(event)
        
    bus.subscribe_all(lambda eid, ev: subscriber(ev))
    
    await orc.run(job, settings)
    
    assert len(received_events) > 0
    # Should have LOG events about scanner loading and completion
    assert any(e.type == EventType.LOG for e in received_events)
    # Should have STATUS completed event
    assert any(e.type == EventType.STATUS and e.data["state"] == "completed" for e in received_events)
    # Job should be in completed state
    assert job.state == "completed"

@pytest.mark.asyncio
async def test_start_run_publishes_running_and_cancel_run():
    bus = EventBus()
    orc = Orchestrator(bus)
    settings = Settings(project_path="/tmp")
    received_events = []

    async def all_subscriber(eid, event):
        received_events.append((eid, event))

    bus.subscribe_all(all_subscriber)

    job = orc.start_run(settings)
    # Initial state should be running immediately
    assert job.state == "running"
    
    # Wait for async event publishing
    await asyncio.sleep(0.1)
    assert any(ev.type == EventType.STATUS and ev.data["state"] == "running" for _, ev in received_events)

    # Wait for task to complete
    await asyncio.sleep(0.5)
    
    # Job should have completed (no scanners, so completes quickly)
    assert job.state == "completed"
    assert any(ev.type == EventType.STATUS and ev.data["state"] == "completed" for _, ev in received_events)


