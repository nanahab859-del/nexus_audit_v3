# core/settings.py
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import asdict
from core.models import Settings
from core.atomic import read_json, write_json

DEFAULT_SETTINGS_PATH = Path("settings.json")

# Module-level lock prevents concurrent read-modify-write races
# between POST /api/settings and POST /api/run.
_lock = asyncio.Lock()


class SettingsManager:
    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH):
        self.path = path
        self.settings: Optional[Settings] = None

    async def load(self) -> Settings:
        async with _lock:
            return await self._load_unsafe()

    async def save(self):
        async with _lock:
            await self._save_unsafe()

    # ── Internal (called only while lock is held) ──────────────────────────
    async def _load_unsafe(self) -> Settings:
        data = await read_json(self.path)
        if data is None:
            # First run — create defaults and persist immediately
            self.settings = Settings(project_path=str(Path.cwd()))
            await self._save_unsafe()
        else:
            # Filter to only known fields so unknown keys in settings.json
            # don't crash Settings(**data) with a TypeError
            import dataclasses
            known = {f.name for f in dataclasses.fields(Settings)}
            filtered = {k: v for k, v in data.items() if k in known}
            self.settings = Settings(**filtered)
        return self.settings

    async def _save_unsafe(self):
        if self.settings:
            await write_json(self.path, asdict(self.settings))
