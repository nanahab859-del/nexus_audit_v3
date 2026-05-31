import importlib
import sys
from pathlib import Path

from plugins.base import BaseScanner, validate_scanner_class


class PluginRegistry:
    """
    Discovers and loads scanner plugins.

    Plugin sub-directories (e.g., plugins/security/, plugins/quality/) must each
    contain an __init__.py file so that importlib.import_module() can resolve them
    as Python packages. A sub-directory without __init__.py will be silently skipped
    during discovery — no error, no crash, but the plugins inside will not be found.
    Phase 3 scanner scaffolding handles this automatically.
    """

    def __init__(self, plugins_dir: Path = Path("plugins")) -> None:
        self.plugins_dir = plugins_dir
        self._registry: dict[str, type[BaseScanner]] = {}
        self._loaded = False

    def load(self) -> None:
        """
        Load all plugins from plugins_dir.
        Idempotent; safe to call multiple times.
        """
        if self._loaded:
            return

        if not self.plugins_dir.exists():
            print(f"Warning: plugins_dir not found: {self.plugins_dir}", file=sys.stderr)
            self._loaded = True
            return

        self._walk_and_load(self.plugins_dir, max_depth=2)
        self._loaded = True

    def _walk_and_load(self, directory: Path, current_depth: int = 0, max_depth: int = 2) -> None:
        """Recursively walk and load plugins up to max_depth."""
        if current_depth > max_depth:
            return

        for item in directory.iterdir():
            if item.is_file() and item.suffix == ".py" and item.name != "__init__.py":
                self._load_file(item)
            elif item.is_dir() and current_depth < max_depth:
                self._walk_and_load(item, current_depth + 1, max_depth)

    def _load_file(self, py_file: Path) -> None:
        """Load a single .py file and discover scanner classes."""
        try:
            module_path = (
                py_file.relative_to(Path("."))
                .with_suffix("")
                .as_posix()
                .replace("/", ".")
            )
            module = importlib.import_module(module_path)

            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseScanner)
                    and obj is not BaseScanner
                ):
                    errors = validate_scanner_class(obj)
                    if errors:
                        for error in errors:
                            print(
                                f"Warning: plugin {obj.__name__} validation failed: {error}",
                                file=sys.stderr,
                            )
                    else:
                        if obj.name in self._registry:
                            print(
                                f"Warning: duplicate scanner name: {obj.name}, overwriting",
                                file=sys.stderr,
                            )
                        self._registry[obj.name] = obj

        except (ImportError, SyntaxError) as e:
            print(f"Warning: failed to load {py_file}: {e}", file=sys.stderr)

    def get(self, name: str) -> type[BaseScanner] | None:
        """Get scanner class by name."""
        return self._registry.get(name)

    def all(self) -> list[type[BaseScanner]]:
        """Get all registered scanner classes."""
        return list(self._registry.values())

    def names(self) -> list[str]:
        """Get all registered scanner names."""
        return list(self._registry.keys())
