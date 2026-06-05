from collections import deque
from typing import Callable, Awaitable, Dict, Set
from dataclasses import dataclass
from enum import Enum

class EventType(Enum):
    STATUS = "status"
    PROGRESS = "progress"
    LOG = "log"
    FINDING = "finding"

@dataclass
class Event:
    type: EventType
    data: dict

class EventBus:
    def __init__(self):
        self._event_counter: int = 0
        self._history: deque[tuple[int, Event]] = deque(maxlen=500)
        self._subscribers: Dict[EventType, Set[Callable[[Event], Awaitable]]] = {et: set() for et in EventType}
        self._all_subscribers: Set[Callable[[int, Event], Awaitable]] = set()

    async def publish(self, event_type: EventType, data: dict):
        self._event_counter += 1
        event = Event(type=event_type, data=data)
        self._history.append((self._event_counter, event))
        
        # Call type-specific subscribers
        for sub in self._subscribers[event_type]:
            await sub(event)
            
        # Call all-subscribers
        for sub in self._all_subscribers:
            await sub(self._event_counter, event)

    def subscribe(self, event_type: EventType, callback: Callable[[Event], Awaitable]):
        self._subscribers[event_type].add(callback)

    def subscribe_all(self, callback: Callable[[int, Event], Awaitable]):
        self._all_subscribers.add(callback)
        
    def get_history(self, since_id: int) -> list[tuple[int, Event]]:
        return [(eid, ev) for eid, ev in self._history if eid > since_id]
