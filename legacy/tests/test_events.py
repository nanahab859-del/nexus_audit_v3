import pytest
from core.events import EventBus, Event, EventType
from datetime import timezone

UTC = timezone.utc


@pytest.mark.asyncio
async def test_publish_calls_subscriber() -> None:
    """Test that publish delivers to subscriber."""
    bus = EventBus()
    received: list[Event] = []

    async def callback(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.LOG, callback)
    event = Event(EventType.LOG, {"level": "info", "message": "test"})
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].type == EventType.LOG


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    """Test that unsubscribe stops delivery."""
    bus = EventBus()
    received: list[Event] = []

    async def callback(event: Event) -> None:
        received.append(event)

    token = bus.subscribe(EventType.LOG, callback)
    bus.unsubscribe(token)

    event = Event(EventType.LOG, {"level": "info", "message": "test"})
    await bus.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_multiple_subscribers() -> None:
    """Test that multiple subscribers all receive."""
    bus = EventBus()
    received1: list[Event] = []
    received2: list[Event] = []

    async def callback1(event: Event) -> None:
        received1.append(event)

    async def callback2(event: Event) -> None:
        received2.append(event)

    bus.subscribe(EventType.LOG, callback1)
    bus.subscribe(EventType.LOG, callback2)

    event = Event(EventType.LOG, {"level": "info", "message": "test"})
    await bus.publish(event)

    assert len(received1) == 1
    assert len(received2) == 1


@pytest.mark.asyncio
async def test_publish_with_no_subscribers() -> None:
    """Test that publish with no subscribers doesn't crash."""
    bus = EventBus()
    event = Event(EventType.LOG, {"level": "info", "message": "test"})
    await bus.publish(event)  # Should not raise


@pytest.mark.asyncio
async def test_subscriber_exception_doesnt_block_others() -> None:
    """Test that exception in one subscriber doesn't block others."""
    bus = EventBus()
    received: list[Event] = []

    async def bad_callback(event: Event) -> None:
        raise ValueError("test error")

    async def good_callback(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.LOG, bad_callback)
    bus.subscribe(EventType.LOG, good_callback)

    event = Event(EventType.LOG, {"level": "info", "message": "test"})
    await bus.publish(event)

    assert len(received) == 1


def test_sync_callback_rejected() -> None:
    """Test that sync callback is rejected."""
    bus = EventBus()

    def sync_callback(event: Event) -> None:
        pass

    with pytest.raises(TypeError, match="EventBus.subscribe requires an async callback"):
        bus.subscribe(EventType.LOG, sync_callback)


def test_async_callback_accepted() -> None:
    """Test that async callback is accepted."""
    bus = EventBus()

    async def async_callback(event: Event) -> None:
        pass

    token = bus.subscribe(EventType.LOG, async_callback)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_publish_status() -> None:
    """Test convenience method publish_status."""
    bus = EventBus()
    received: list[Event] = []

    async def callback(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.STATUS, callback)
    await bus.publish_status("running", "job-123")

    assert len(received) == 1
    assert received[0].type == EventType.STATUS
    assert received[0].payload["state"] == "running"
    assert received[0].payload["job_id"] == "job-123"


@pytest.mark.asyncio
async def test_publish_progress() -> None:
    """Test convenience method publish_progress."""
    bus = EventBus()
    received: list[Event] = []

    async def callback(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.PROGRESS, callback)
    await bus.publish_progress("bandit", 50, "app.py")

    assert len(received) == 1
    assert received[0].payload["scanner"] == "bandit"
    assert received[0].payload["percent"] == 50


@pytest.mark.asyncio
async def test_history_after_publishing() -> None:
    """Test that history captures published events."""
    bus = EventBus()

    for i in range(5):
        event = Event(EventType.LOG, {"level": "info", "message": f"msg{i}"})
        await bus.publish(event)

    history = bus.history()
    assert len(history) == 5


@pytest.mark.asyncio
async def test_history_ring_buffer_max() -> None:
    """Test that history ring buffer respects max size."""
    bus = EventBus()

    for i in range(110):
        event = Event(EventType.LOG, {"level": "info", "message": f"msg{i}"})
        await bus.publish(event)

    history = bus.history()
    assert len(history) == 100


@pytest.mark.asyncio
async def test_history_since_index() -> None:
    """Test that history(since_index) returns events from that index."""
    bus = EventBus()

    for i in range(5):
        event = Event(EventType.LOG, {"level": "info", "message": f"msg{i}"})
        await bus.publish(event)

    history_from_3 = bus.history(since_index=3)
    assert len(history_from_3) == 2
