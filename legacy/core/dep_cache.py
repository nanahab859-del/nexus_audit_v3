from typing import Any
import json
import time
from pathlib import Path

class DepCache:
    """
    Caches PyPI/OSV results keyed by (package, version). TTL: 24h.
    force_rescan=True bypasses cache entirely.
    """
    def __init__(self, cache_dir: Path, force_rescan: bool = False, ttl_seconds: float = 86400.0) -> None:
        self.cache_dir = cache_dir
        self.force_rescan = force_rescan
        self.ttl_seconds = ttl_seconds
        self.db_path = self.cache_dir / ".nexus_dep_cache.json"
        self._data: dict[str, Any] = {}
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.db_path.exists():
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def get(self, package: str, version: str) -> dict[str, Any] | None:
        if self.force_rescan:
            return None
            
        key = f"{package}=={version}"
        entry = self._data.get(key)
        
        if not entry:
            return None
            
        timestamp = entry.get("timestamp", 0)
        if time.time() - timestamp > self.ttl_seconds:
            # Expired
            del self._data[key]
            self._save()
            return None
            
        return entry.get("data")

    def set(self, package: str, version: str, data: dict[str, Any]) -> None:
        key = f"{package}=={version}"
        self._data[key] = {
            "timestamp": time.time(),
            "data": data
        }
        self._save()
