"""
Round-robin API key pool with caller-driven rate limiting.
Keys are NOT marked unavailable on successful use.
Call mark_rate_limited(key) only on HTTP 429 / quota errors.
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class _KeyEntry:
    key:               str
    unavailable_until: float = 0.0   # monotonic; 0 = always available


class KeyPool:
    def __init__(
        self,
        primary_key: str,
        extra_keys: Optional[List[str]] = None,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._entries: List[_KeyEntry] = [_KeyEntry(key=primary_key)]
        for k in (extra_keys or []):
            self._entries.append(_KeyEntry(key=k))
        self._index = 0
        self._lock  = asyncio.Lock()

    async def next_key(self) -> Optional[str]:
        """
        Return the next available key in round-robin order.
        Returns None only if ALL keys are currently rate-limited.
        Does NOT mark the returned key unavailable.
        """
        async with self._lock:
            now = monotonic()
            n   = len(self._entries)
            for i in range(n):
                entry = self._entries[(self._index + i) % n]
                if entry.unavailable_until <= now:
                    self._index = (self._index + i + 1) % n
                    return entry.key
            soonest = min(e.unavailable_until for e in self._entries) - now
            logger.warning("All %d key(s) rate-limited. Next available in %.0fs.", n, soonest)
            return None

    async def mark_rate_limited(
        self, key: str, cooldown_seconds: Optional[float] = None
    ) -> None:
        """Mark a specific key as rate-limited. Call on HTTP 429 only."""
        wait = cooldown_seconds if cooldown_seconds is not None else self._cooldown
        async with self._lock:
            for entry in self._entries:
                if entry.key == key:
                    entry.unavailable_until = monotonic() + wait
                    logger.info("Key ...%s rate-limited for %.0fs.", key[-4:], wait)
                    return

    async def add_key(self, key: str) -> None:
        async with self._lock:
            if not any(e.key == key for e in self._entries):
                self._entries.append(_KeyEntry(key=key))

    async def remove_key(self, key: str) -> None:
        async with self._lock:
            self._entries = [e for e in self._entries if e.key != key]
            if self._index >= len(self._entries):
                self._index = 0

    @property
    def total_count(self) -> int:
        return len(self._entries)

    async def available_count(self) -> int:
        now = monotonic()
        async with self._lock:
            return sum(1 for e in self._entries if e.unavailable_until <= now)
