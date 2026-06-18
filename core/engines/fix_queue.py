import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from core.primitives.models import Finding, FixStatus
from core.primitives.atomic import read_json, write_json

logger = logging.getLogger(__name__)

@dataclass
class SyncResult:
    reappeared: List[str]
    new_count: int
    persistent_count: int
    resolved_count: int

class FixQueue:
    def __init__(self, queue_path: Path):
        self._path = queue_path
        self._data: Dict[str, dict] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    @staticmethod
    def fingerprint(finding: Finding) -> str:
        rule_id = finding.rule_id or finding.scanner or "unknown"
        file_path = finding.file
        snippet = finding.snippet or ""
        
        # Normalize snippet: first 200 chars, stripped, whitespace collapsed
        s = snippet.strip()[:200]
        s = " ".join(s.split())
        if not s:
            s = f"{finding.title} | {finding.description}"
        
        hash_input = f"{rule_id}|{file_path}|{s}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _load(self) -> None:
        if self._loaded:
            return
        
        if self._path.exists():
            try:
                data = await read_json(self._path)
                self._data = data if isinstance(data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to load fix queue: {e}")
                self._data = {}
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data = {}
        self._loaded = True

    async def _save(self) -> None:
        await write_json(self._path, self._data, indent=4)

    # ── Public API for CLI handlers ────────────────────────────────────────────

    async def load(self) -> None:
        """Public alias for _load(). Called by CLI handlers."""
        await self._load()

    def entries(self) -> list:
        """Return all fix queue entries as a list of dicts."""
        return list(self._data.values())

    def get_entry(self, fingerprint: str) -> Optional[dict]:
        """
        Return the entry for the given fingerprint, or None.
        Supports prefix matching (first N chars) for usability at the CLI.
        """
        if fingerprint in self._data:
            return self._data[fingerprint]
        for key, entry in self._data.items():
            if key.startswith(fingerprint):
                return entry
        return None

    async def get_status(self, fingerprint: str) -> Optional[str]:
        async with self._lock:
            await self._load()
            entry = self._data.get(fingerprint)
            return entry.get("status") if isinstance(entry, dict) else entry

    async def update_status(self, fingerprint: str, status: str, note: str = "") -> None:
        async with self._lock:
            await self._load()
            entry = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
            if note:
                entry["note"] = note
            self._data[fingerprint] = entry
            await self._save()

    async def sync(self, current_findings: List[Finding]) -> SyncResult:
        async with self._lock:
            await self._load()
            current_fps = {self.fingerprint(f) for f in current_findings}
            reappeared = []
            new_count = 0
            persistent_count = 0
            resolved_count = 0
            now = datetime.now(timezone.utc)

            for fp in current_fps:
                if fp in self._data:
                    entry = self._data[fp]
                    if isinstance(entry, dict) and entry.get("status") == FixStatus.DONE.value:
                        entry["status"] = FixStatus.OPEN.value
                        entry["updated_at"] = now.isoformat()
                        reappeared.append(fp)
                    else:
                        persistent_count += 1
                else:
                    self._data[fp] = {"status": FixStatus.OPEN.value, "updated_at": now.isoformat()}
                    new_count += 1

            # Pruning
            to_delete = []
            for fp, entry in self._data.items():
                if fp not in current_fps and isinstance(entry, dict) and entry.get("status") == FixStatus.DONE.value:
                    updated_at = datetime.fromisoformat(entry.get("updated_at", now.isoformat()))
                    if now - updated_at > timedelta(days=30):
                        to_delete.append(fp)
                    else:
                        resolved_count += 1
            
            for fp in to_delete:
                del self._data[fp]

            await self._save()
            return SyncResult(reappeared, new_count, persistent_count, resolved_count)
