from pathlib import Path
from typing import List
from plugins.base import BaseScanner
from core.models import Finding, Category
from core.events import EventBus, EventType

class VultureScanner(BaseScanner):
    name = "vulture"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 0, "file": ""})
        # Simulate scanning
        await bus.publish(EventType.PROGRESS, {"scanner": self.name, "percent": 100, "file": ""})
        return []
