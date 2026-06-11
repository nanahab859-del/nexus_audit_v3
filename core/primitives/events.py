import asyncio
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Awaitable, Dict, List, Optional, Tuple, Union
from collections import deque

# --- 1. EventType Enum ---
class EventType(Enum):
    STATUS = "status"
    PROGRESS = "progress"
    LOG = "log"
    FINDING = "finding"
    SYSTEM = "system"

# --- 2. Event Dataclass ---
@dataclass(frozen=True)
class Event:
    type: EventType
    payload: dict
    timestamp: datetime   # UTC-aware, set at publish time

# --- 3. EventBus Class ---
class EventBus:
    def __init__(self, history_size: int = 5000):
        self._counter: int = 0
        self._history: deque[Tuple[int, Event]] = deque(maxlen=history_size)
        self._subscribers: Dict[EventType, List[Callable[[Event], Awaitable]]] = {
            et: [] for et in EventType
        }
        self._all_subscribers: List[Callable[[int, Event], Awaitable]] = []
        self._tokens: Dict[str, Tuple[Optional[EventType], Callable]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event_type: EventType, data: dict) -> None:
        async with self._lock:
            self._counter += 1
            event = Event(type=event_type, payload=data, timestamp=datetime.now(timezone.utc))
            self._history.append((self._counter, event))
            
            # Copy subscriber lists
            type_subscribers = list(self._subscribers.get(event_type, []))
            all_subs = list(self._all_subscribers)
            
        # Release lock
        
        # Schedule subscribers
        tasks = []
        
        for sub in type_subscribers:
            tasks.append(self._safe_notify(sub, event))
            
        for sub in all_subs:
            tasks.append(self._safe_notify_all(sub, self._counter, event))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_notify(self, callback: Callable[[Event], Awaitable], event: Event):
        try:
            await callback(event)
        except Exception as e:
            logging.warning(f"Subscriber error: {e}")

    async def _safe_notify_all(self, callback: Callable[[int, Event], Awaitable], event_id: int, event: Event):
        try:
            await callback(event_id, event)
        except Exception as e:
            logging.warning(f"Subscriber error: {e}")

    def subscribe(self, event_type: EventType, callback: Callable[[Event], Awaitable]) -> str:
        token = str(uuid.uuid4())
        self._subscribers[event_type].append(callback)
        self._tokens[token] = (event_type, callback)
        return token

    def subscribe_all(self, callback: Callable[[int, Event], Awaitable]) -> str:
        token = str(uuid.uuid4())
        self._all_subscribers.append(callback)
        self._tokens[token] = (None, callback)
        return token

    def unsubscribe(self, token: str) -> None:
        if token not in self._tokens:
            return
        
        event_type, callback = self._tokens[token]
        if event_type is None:
            if callback in self._all_subscribers:
                self._all_subscribers.remove(callback)
        else:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
        
        del self._tokens[token]

    def get_history(self, since_id: int = 0) -> List[Tuple[int, Event]]:
        return [(eid, ev) for eid, ev in self._history if eid > since_id]

    # --- 4. Convenience Methods ---
    async def publish_status(self, state: str, job_id: Optional[str] = None) -> None:
        await self.publish(EventType.STATUS, {"state": state, "job_id": job_id})

    async def publish_progress(self, scanner: str, percent: int, file: str = "") -> None:
        await self.publish(EventType.PROGRESS, {"scanner": scanner, "percent": percent, "file": file})

    async def publish_log(self, level: str, message: str) -> None:
        await self.publish(EventType.LOG, {"level": level, "message": message})

    async def publish_finding(self, finding) -> None:
        from core.primitives.models import finding_to_dict
        await self.publish(EventType.FINDING, {"finding": finding_to_dict(finding)})
