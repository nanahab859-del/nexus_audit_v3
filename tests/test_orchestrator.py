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
    assert any(e.type == EventType.PROGRESS for e in received_events)
    assert any(e.type == EventType.STATUS and e.data["state"] == "completed" for e in received_events)
