from abc import ABC, abstractmethod
from typing import ClassVar, List
from pathlib import Path
from core.models import Finding, Category
from core.events import EventBus
import re

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

def validate_scanner_class(cls: type) -> list[str]:
    """
    Validate a scanner class.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    # Check ClassVar fields
    required = ["name", "version", "languages", "category"]
    for field_name in required:
        if not hasattr(cls, field_name):
            errors.append(f"Missing ClassVar: {field_name}")

    # Check name format
    if hasattr(cls, "name"):
        name = getattr(cls, "name")
        if not isinstance(name, str):
            errors.append(f"name must be str, got {type(name).__name__}")
        elif not re.match(r"^[a-z0-9_-]+$", name):
            errors.append(f"name must match [a-z0-9_-]+, got: {name}")

    # Check languages non-empty
    if hasattr(cls, "languages"):
        langs = getattr(cls, "languages")
        if not isinstance(langs, list) or len(langs) == 0:
            errors.append("languages must be non-empty list")

    # Check category is Category enum
    if hasattr(cls, "category"):
        cat = getattr(cls, "category")
        if not isinstance(cat, Category):
            errors.append(f"category must be Category enum, got {type(cat).__name__}")

    # Check scan is implemented
    if not hasattr(cls, "scan") or cls.scan is BaseScanner.scan:
        errors.append("scan() must be implemented")

    return errors

