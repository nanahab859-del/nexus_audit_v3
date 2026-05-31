import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from core.events import EventBus
from core.models import Category, Finding


class BaseScanner(ABC):
    """Abstract base class for all scanners."""

    name: ClassVar[str]
    version: ClassVar[str]
    languages: ClassVar[list[str]]
    category: ClassVar[Category]
    requires_ai: ClassVar[bool] = False
    timeout: ClassVar[int] = 300

    @abstractmethod
    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list[Finding]:
        """Scan target and return findings."""
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
