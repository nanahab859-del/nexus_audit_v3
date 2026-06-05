import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

UTC = timezone.utc


class EventType(Enum):
    """Event types emitted on the bus."""
    STATUS = "status"
    PROGRESS = "progress"
    LOG = "log"
    FINDING = "finding"


@dataclass(frozen=True)
class Event:
    """Immutable event on the bus."""
    type: EventType
    payload: dict[str, Any]
    timestamp: datetime = None  # type: ignore

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(UTC))


class EventBus:
    """In-process async pub-sub."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, dict[str, Callable[[Event], Any]]] = {
            et: {} for et in EventType
        }
        self._next_token = 0
        self._lock = asyncio.Lock()
        self._history: list[Event] = []
        self._history_max: int = 100

    def subscribe(
        self, event_type: EventType, callback: Callable[[Event], Any]
    ) -> str:
        """
        Subscribe to events of a type.
        Callback must be async.
        Returns opaque token for unsubscribing.
        """
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(
                f"EventBus.subscribe requires an async callback, "
                f"got {type(callback).__name__}: {callback!r}"
            )

        token = str(self._next_token)
        self._next_token += 1
        self._subscribers[event_type][token] = callback
        return token

    def unsubscribe(self, token: str) -> None:
        """Unsubscribe. Unknown token is a no-op."""
        for event_type in EventType:
            self._subscribers[event_type].pop(token, None)

    async def publish(self, event: Event) -> None:
        """Publish event to all subscribers. Exceptions in callbacks are caught."""
        async with self._lock:
            callbacks = list(self._subscribers[event.type].values())

        tasks = [cb(event) for cb in callbacks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Error in event subscriber: {result}", file=sys.stderr)

        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max:]

    async def publish_status(self, state: str, job_id: str | None) -> None:
        """Publish status event."""
        await self.publish(
            Event(EventType.STATUS, {"state": state, "job_id": job_id})
        )

    async def publish_progress(self, scanner: str, percent: int, file: str) -> None:
        """Publish progress event."""
        await self.publish(
            Event(
                EventType.PROGRESS,
                {"scanner": scanner, "percent": percent, "file": file},
            )
        )

    async def publish_log(self, level: str, message: str) -> None:
        """Publish log event."""
        await self.publish(Event(EventType.LOG, {"level": level, "message": message}))

    async def publish_finding(self, finding: dict[str, Any]) -> None:
        """Publish finding event."""
        await self.publish(Event(EventType.FINDING, {"finding": finding}))

    def history(self, since_index: int = 0) -> list[Event]:
        """
        Return events from the ring buffer starting at since_index.
        Phase 2 SSE route passes the client's Last-Event-ID as since_index.
        Returns an empty list if since_index >= current buffer length.
        """
        return self._history[since_index:]


# Module-level singleton
bus = EventBus()
