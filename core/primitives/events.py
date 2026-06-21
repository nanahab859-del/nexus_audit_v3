"""
events.py — EventBus for the Nexus Audit pipeline.

Provides publish/subscribe with:
  - UTC-aware timestamps on every event
  - Bounded history deque (default 5000 events)
  - Token-based subscription and unsubscription
  - Safe notification: subscriber errors are caught and logged, never propagate
  - Support for both sync and async subscriber callbacks
  - Lock-guarded subscriber list mutations (subscribe/unsubscribe are async)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class EventType(Enum):
    STATUS        = "status"
    PROGRESS      = "progress"
    LOG           = "log"
    FINDING       = "finding"
    FINDING_BATCH = "finding_batch"
    SYSTEM        = "system"


@dataclass(frozen=True)
class Event:
    type:      EventType
    payload:   dict
    timestamp: datetime   # always UTC-aware


class EventBus:
    """
    Central event bus for the audit pipeline.

    Subscribers register callbacks (sync or async). On publish, all registered
    callbacks for the event type are called concurrently via asyncio.gather.
    Errors in one subscriber do not affect others.

    subscribe(), subscribe_all(), and unsubscribe() are all async so they can
    be lock-guarded without blocking the event loop.
    """

    def __init__(self, history_size: int = 5000) -> None:
        self._counter:         int   = 0
        self._history:         deque = deque(maxlen=history_size)
        self._subscribers:     Dict[EventType, List[Callable]] = {
            et: [] for et in EventType
        }
        self._all_subscribers: List[Callable] = []
        self._tokens:          Dict[str, Tuple[Optional[EventType], Callable]] = {}
        self._lock = asyncio.Lock()

    # ── Core publish ───────────────────────────────────────────────────────────

    async def publish(self, event_type: EventType, data: dict) -> None:
        async with self._lock:
            self._counter += 1
            seq_id = self._counter
            event  = Event(
                type=event_type,
                payload=data,
                timestamp=datetime.now(timezone.utc),
            )
            self._history.append((seq_id, event))
            type_subs = list(self._subscribers.get(event_type, []))
            all_subs  = list(self._all_subscribers)

        # Notify outside the lock so subscribers can publish new events
        tasks = (
            [self._safe_notify(cb, event) for cb in type_subs]
            + [self._safe_notify_all(cb, seq_id, event) for cb in all_subs]
        )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Subscribe / unsubscribe (async + lock-guarded) ─────────────────────────

    async def subscribe(
        self,
        event_type: EventType,
        callback: Callable,
    ) -> str:
        """
        Register a callback for a specific event type.
        Accepts both sync and async callables.
        Returns an opaque token for later unsubscription.
        Must be awaited: token = await bus.subscribe(EventType.LOG, my_fn)
        """
        token = str(uuid.uuid4())
        async with self._lock:
            self._subscribers[event_type].append(callback)
            self._tokens[token] = (event_type, callback)
        return token

    async def subscribe_all(self, callback: Callable) -> str:
        """
        Register a callback that receives every event regardless of type.
        Must be awaited: token = await bus.subscribe_all(my_fn)
        """
        token = str(uuid.uuid4())
        async with self._lock:
            self._all_subscribers.append(callback)
            self._tokens[token] = (None, callback)
        return token

    async def unsubscribe(self, token: str) -> None:
        """
        Remove the subscriber associated with the given token.
        Must be awaited: await bus.unsubscribe(token)
        """
        async with self._lock:
            if token not in self._tokens:
                return
            event_type, callback = self._tokens.pop(token)
            if event_type is None:
                try:
                    self._all_subscribers.remove(callback)
                except ValueError:
                    pass
            else:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    def get_history(self, since_id: int = 0) -> List[Tuple[int, Event]]:
        """Return all events with sequence ID greater than since_id."""
        return [(eid, ev) for eid, ev in self._history if eid > since_id]

    # ── Convenience publishers ─────────────────────────────────────────────────

    async def publish_status(
        self, state: str, job_id: Optional[str] = None
    ) -> None:
        await self.publish(EventType.STATUS, {"state": state, "job_id": job_id})

    async def publish_progress(
        self, scanner: str, percent: int, file: str = ""
    ) -> None:
        await self.publish(
            EventType.PROGRESS,
            {"scanner": scanner, "percent": percent, "file": file},
        )

    async def publish_log(self, level: str, message: str) -> None:
        await self.publish(EventType.LOG, {"level": level, "message": message})

    async def publish_finding(self, finding) -> None:
        """Publish a single finding. For bulk use publish_finding_batch."""
        from core.primitives.models import to_dict
        await self.publish(EventType.FINDING, {"finding": to_dict(finding)})

    async def publish_finding_batch(self, findings: list) -> None:
        """
        Publish multiple findings in one event.
        Reduces asyncio.gather() fan-outs for high-volume scans.
        """
        from core.primitives.models import to_dict
        await self.publish(
            EventType.FINDING_BATCH,
            {"findings": [to_dict(f) for f in findings]},
        )

    # ── Internal notification ──────────────────────────────────────────────────

    async def _safe_notify(self, callback: Callable, event: Event) -> None:
        """
        Call a subscriber callback safely.
        Handles both sync and async callbacks — checks iscoroutine before awaiting.
        Errors are caught and logged; they never propagate to the publisher.
        """
        try:
            result = callback(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning("EventBus subscriber error: %s", e)

    async def _safe_notify_all(
        self,
        callback: Callable,
        event_id: int,
        event: Event,
    ) -> None:
        try:
            result = callback(event_id, event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning("EventBus global subscriber error: %s", e)
