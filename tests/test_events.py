import pytest
import asyncio
from core.events import EventBus, EventType

@pytest.mark.asyncio
async def test_event_bus():
    bus = EventBus()
    received_events = []
    
    async def subscriber(event):
        received_events.append(event)
        
    bus.subscribe(EventType.LOG, subscriber)
    await bus.publish(EventType.LOG, {"message": "hello"})
    
    assert len(received_events) == 1
    assert received_events[0].data["message"] == "hello"
    assert bus.get_history(0)[0][0] == 1

@pytest.mark.asyncio
async def test_event_bus_all_subscribers():
    bus = EventBus()
    received_events = []
    
    async def all_subscriber(eid, event):
        received_events.append((eid, event))
        
    bus.subscribe_all(all_subscriber)
    await bus.publish(EventType.STATUS, {"state": "running"})
    
    assert len(received_events) == 1
    assert received_events[0][0] == 1
    assert received_events[0][1].type == EventType.STATUS
