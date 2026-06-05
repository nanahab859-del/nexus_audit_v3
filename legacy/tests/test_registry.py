from pathlib import Path
from core.registry import PluginRegistry
from plugins.base import BaseScanner
from core.models import Category
from core.events import EventBus


class ValidScanner(BaseScanner):
    """Test scanner."""
    name = "valid-scanner"
    version = "1.0.0"
    languages = ["python"]
    category = Category.SECURITY

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> list:
        return []


def test_registry_creation() -> None:
    """Test PluginRegistry creation."""
    registry = PluginRegistry(Path("plugins"))
    assert registry.plugins_dir == Path("plugins")


def test_registry_load_idempotent(tmp_path: Path) -> None:
    """Test that load() is idempotent."""
    registry = PluginRegistry(tmp_path)
    registry.load()
    registry.load()  # Should not crash


def test_registry_missing_dir(tmp_path: Path) -> None:
    """Test that missing plugins_dir logs warning and continues."""
    missing = tmp_path / "nonexistent"
    registry = PluginRegistry(missing)
    registry.load()  # Should not crash


def test_get_returns_none_for_missing() -> None:
    """Test that get() returns None for missing scanner."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()
    result = registry.get("nonexistent")
    assert result is None


def test_all_returns_list() -> None:
    """Test that all() returns list."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()
    result = registry.all()
    assert isinstance(result, list)


def test_names_returns_list() -> None:
    """Test that names() returns list."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()
    result = registry.names()
    assert isinstance(result, list)
