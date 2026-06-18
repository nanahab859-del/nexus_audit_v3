import asyncio
import atexit
import time
import logging
from pathlib import Path
from typing import Optional
from core.primitives.atomic import read_json, write_json

logger = logging.getLogger(__name__)

class DepCache:
    DEFAULT_TTL = 86400  # 24 hours in seconds

    def __init__(self, cache_path: Path = Path.home() / ".nexus_audit" / "dep_cache.json"):
        self._path = cache_path
        self._data: dict[str, dict] = {}
        self._loaded = False
        self._dirty = False
        self._lock = asyncio.Lock()
        atexit.register(self._sync_save_on_exit)

    def _cache_key(self, package: str, version: str) -> str:
        # Normalize: strip, lower, hyphen to underscore
        norm_pkg = package.strip().lower().replace("-", "_")
        return f"{norm_pkg}=={version.strip()}"

    async def _load_internal(self) -> None:
        if self._loaded:
            return
        
        if self._path.exists():
            try:
                data = await read_json(self._path)
                if isinstance(data, dict):
                    self._data = data
                else:
                    logger.warning(f"Corrupt cache file: {self._path}")
                    self._data = {}
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                self._data = {}
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data = {}
        
        self._loaded = True

    async def get(self, package: str, version: str, force_rescan: bool = False) -> Optional[dict]:
        async with self._lock:
            if not self._loaded:
                await self._load_internal()
            
            if force_rescan:
                return None
            
            key = self._cache_key(package, version)
            entry = self._data.get(key)
            
            if not entry:
                return None
            
            cached_at = entry.get("cached_at", 0)
            if time.time() - cached_at > self.DEFAULT_TTL:
                return None
                
            return entry.get("data")

    async def set(self, package: str, version: str, data: dict) -> None:
        async with self._lock:
            if not self._loaded:
                await self._load_internal()
            key = self._cache_key(package, version)
            self._data[key] = {"cached_at": time.time(), "data": data}
            self._dirty = True

    async def save(self) -> None:
        async with self._lock:
            await self._save_internal()

    async def _save_internal(self) -> None:
        if self._dirty:
            await write_json(self._path, self._data)
            self._dirty = False

    async def clear(self) -> None:
        async with self._lock:
            self._data = {}
            self._dirty = True
            await self._save_internal()

    def _sync_save_on_exit(self) -> None:
        """Best-effort synchronous save at interpreter exit."""
        if not self._dirty:
            return
        try:
            import json
            self._path.write_text(
                json.dumps(self._data, default=str), encoding="utf-8"
            )
        except Exception:
            pass   # logging is unreliable during shutdown

    async def __aenter__(self) -> "DepCache":
        await self._load_internal()
        return self

    async def __aexit__(self, *_) -> None:
        await self.save()
