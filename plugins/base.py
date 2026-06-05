from abc import ABC, abstractmethod
from typing import ClassVar, List
from pathlib import Path
from core.models import Finding, Category
from core.events import EventBus

class BaseScanner(ABC):
    name: ClassVar[str]
    version: ClassVar[str]
    languages: ClassVar[List[str]]
    category: ClassVar[Category]
    requires_ai: ClassVar[bool] = False
    timeout: ClassVar[int] = 120

    @abstractmethod
    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        ...
