from pathlib import Path
from typing import Optional
from dataclasses import asdict
from core.models import Settings
from core.atomic import read_json, write_json

DEFAULT_SETTINGS_PATH = Path("settings.json")

class SettingsManager:
    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH):
        self.path = path
        self.settings: Optional[Settings] = None

    async def load(self) -> Settings:
        data = await read_json(self.path)
        if data is None:
            # Create default settings
            self.settings = Settings(project_path=str(Path.cwd()))
            await self.save()
        else:
            self.settings = Settings(**data)
        return self.settings

    async def save(self):
        if self.settings:
            await write_json(self.path, asdict(self.settings))
