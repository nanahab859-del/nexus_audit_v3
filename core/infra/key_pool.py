import asyncio
import time
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)

@dataclass
class KeyEntry:
    key: str
    exhausted_until: float = 0.0

class KeyPool:
    def __init__(
        self,
        provider: str,
        primary_key: str,
        extra_keys: List[str] = None,
        cooldown_seconds: int = 60,
        max_keys: int = 20
    ):
        self.provider = provider
        self.cooldown_seconds = cooldown_seconds
        self.max_keys = max_keys
        
        # Initialize keys
        self._keys: List[KeyEntry] = []
        if primary_key:
            self._keys.append(KeyEntry(key=primary_key))
        if extra_keys:
            for k in extra_keys:
                if len(self._keys) < self.max_keys:
                    self._keys.append(KeyEntry(key=k))
        
        self._lock = asyncio.Lock()
        
        logger.info(f"KeyPool initialized with {len(self._keys)} keys for {self.provider}")
        if len(self._keys) == 0:
            logger.warning(f"KeyPool initialized with 0 keys for {self.provider}")

    async def add_key(self, key: str) -> None:
        async with self._lock:
            if len(self._keys) < self.max_keys:
                self._keys.append(KeyEntry(key=key))

    async def next_key(self) -> Optional[str]:
        async with self._lock:
            now = time.time()
            for entry in self._keys:
                if entry.exhausted_until > 0 and now >= entry.exhausted_until:
                    entry.exhausted_until = 0.0  # re-enable
                
                if entry.exhausted_until == 0.0:
                    entry.exhausted_until = now + self.cooldown_seconds
                    return entry.key
        
        logger.critical(f"All API keys for {self.provider} are exhausted.")
        return None

    async def mark_exhausted(self, key: str) -> None:
        async with self._lock:
            now = time.time()
            for entry in self._keys:
                if entry.key == key:
                    entry.exhausted_until = now + self.cooldown_seconds
                    break

    async def remove_key(self, key: str) -> None:
        async with self._lock:
            self._keys = [e for e in self._keys if e.key != key]

    async def available_count(self) -> int:
        async with self._lock:
            now = time.time()
            return sum(1 for e in self._keys if e.exhausted_until == 0.0 or now >= e.exhausted_until)

    async def total_count(self) -> int:
        async with self._lock:
            return len(self._keys)
