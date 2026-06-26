import pytest
import asyncio
import logging
from core.primitives.events import EventBus, EventType
from core.primitives.models import Finding, Severity, Category

@pytest.mark.asyncio
async def test_subscriber_exception_isolated(caplog):
    bus = EventBus()

    async def callback1(evt):
        raise RuntimeError("boom")

    called2 = False
    async def callback2(evt):
        nonlocal called2
        called2 = True

    await bus.subscribe(EventType.LOG, callback1)
    await bus.subscribe(EventType.LOG, callback2)

    with caplog.at_level(logging.WARNING):
        await bus.publish(EventType.LOG, {"level": "info", "message": "test"})

    assert called2 is True
    assert "boom" in caplog.text

@pytest.mark.asyncio
async def test_subscribe_all_multiple_callbacks():
    bus = EventBus()
    count = 0

    async def cb1(evt_id, evt):
        nonlocal count
        count += 1

    async def cb2(evt_id, evt):
        nonlocal count
        count += 1

    await bus.subscribe_all(cb1)
    await bus.subscribe_all(cb2)

    await bus.publish(EventType.STATUS, {"state": "running"})
    assert count == 2

@pytest.mark.asyncio
async def test_unsubscribe_then_resubscribe():
    bus = EventBus()
    calls1 = []
    calls2 = []

    async def cb1(evt): calls1.append(evt)
    async def cb2(evt): calls2.append(evt)

    token1 = await bus.subscribe(EventType.LOG, cb1)
    await bus.unsubscribe(token1)
    await bus.subscribe(EventType.LOG, cb2)

    await bus.publish(EventType.LOG, {"message": "test"})
    assert len(calls1) == 0
    assert len(calls2) == 1

@pytest.mark.asyncio
async def test_ring_buffer_exact_maxlen():
    bus = EventBus(history_size=3)
    await bus.publish(EventType.LOG, {"m": 1})
    await bus.publish(EventType.LOG, {"m": 2})
    await bus.publish(EventType.LOG, {"m": 3})
    assert len(bus.get_history()) == 3

    await bus.publish(EventType.LOG, {"m": 4})
    await bus.publish(EventType.LOG, {"m": 5})
    history = bus.get_history()
    assert len(history) == 3
    assert history[0][1].payload["m"] == 3
    assert history[2][1].payload["m"] == 5

@pytest.mark.asyncio
async def test_get_history_returns_correct_events():
    bus = EventBus(history_size=10)
    for i in range(5):
        await bus.publish(EventType.LOG, {"i": i+1})

    # IDs start at 1
    history = bus.get_history(since_id=2)
    assert len(history) == 3
    assert history[0][1].payload["i"] == 3

@pytest.mark.asyncio
async def test_get_history_since_id_zero():
    bus = EventBus(history_size=10)
    for i in range(3):
        await bus.publish(EventType.LOG, {"i": i+1})
    history = bus.get_history(since_id=0)
    assert len(history) == 3

@pytest.mark.asyncio
async def test_concurrent_publish():
    bus = EventBus(history_size=10)
    async def pub(i):
        await bus.publish(EventType.LOG, {"i": i})

    await asyncio.gather(*(pub(i) for i in range(10)))
    assert len(bus.get_history()) == 10
    ids = {evt.payload["i"] for eid, evt in bus.get_history()}
    assert ids == set(range(10))

@pytest.mark.asyncio
async def test_safe_notify_error_handling(caplog):
    # Covers: _safe_notify exception logging
    bus = EventBus()
    async def bad_sub(evt): raise Exception("bad")
    await bus.subscribe(EventType.LOG, bad_sub)
    with caplog.at_level(logging.WARNING):
        await bus.publish(EventType.LOG, {"m": "test"})
    assert "subscriber error" in caplog.text.lower()

@pytest.mark.asyncio
async def test_unsubscribe_all():
    bus = EventBus()
    calls = []
    async def cb(id, evt): calls.append(evt)

    token = await bus.subscribe_all(cb)
    await bus.unsubscribe(token)

    await bus.publish(EventType.LOG, {"m": "test"})
    assert len(calls) == 0

@pytest.mark.asyncio
async def test_convenience_methods():
    bus = EventBus()
    # Mock to check calls
    events = []
    await bus.subscribe_all(lambda id, evt: events.append(evt))

    await bus.publish_status("test-status", "test-job")
    await bus.publish_progress("test-scanner", 50, "test-file")
    await bus.publish_log("info", "test-log")

    assert any(e.type == EventType.STATUS for e in events)
    assert any(e.type == EventType.PROGRESS for e in events)
    assert any(e.type == EventType.LOG for e in events)

@pytest.mark.asyncio
async def test_publish_status_convenience_method():
    bus = EventBus()
    received = []
    await bus.subscribe(EventType.STATUS, lambda evt: received.append(evt))
    await bus.publish_status("running", "job-123")
    assert received[0].payload == {"state": "running", "job_id": "job-123"}

@pytest.mark.asyncio
async def test_publish_finding_convenience_method():
    bus = EventBus()
    received = []
    await bus.subscribe(EventType.FINDING, lambda evt: received.append(evt))
    f = Finding(id="1", rule_id="r", scanner="s", file="f", line=1, column=0, severity=Severity.LOW, category=Category.QUALITY, title="t", description="d")
    await bus.publish_finding(f)
    assert "finding" in received[0].payload

@pytest.mark.asyncio
async def test_unsubscribe_all_tokens():
    bus = EventBus()
    calls1, calls2, calls3 = [], [], []
    t1 = await bus.subscribe(EventType.LOG, lambda evt: calls1.append(evt))
    t2 = await bus.subscribe(EventType.STATUS, lambda evt: calls2.append(evt))
    t3 = await bus.subscribe_all(lambda id, evt: calls3.append(evt))

    await bus.unsubscribe(t1)
    await bus.unsubscribe(t2)
    await bus.unsubscribe(t3)

    await bus.publish(EventType.LOG, {"m": "test"})
    await bus.publish(EventType.STATUS, {"m": "test"})
    assert len(calls1) == 0
    assert len(calls2) == 0
    assert len(calls3) == 0

@pytest.mark.asyncio
async def test_unsubscribe_invalid_token():
    bus = EventBus()
    await bus.unsubscribe("invalid-token") # Should not raise

@pytest.mark.asyncio
async def test_unsubscribe_remove_failed():
    bus = EventBus()
    async def cb(evt): pass
    # Subscribe and manually remove to simulate callback not in list
    token = await bus.subscribe(EventType.LOG, cb)
    bus._subscribers[EventType.LOG].remove(cb)
    await bus.unsubscribe(token) # Should not raise
