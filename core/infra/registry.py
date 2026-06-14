import importlib.util
import logging
import uuid
import inspect
from pathlib import Path
from typing import Optional, Dict, List
from core.primitives.events import EventBus
from plugins.base import BaseScanner, validate_scanner_class

logger = logging.getLogger(__name__)

class PluginRegistry:
    def __init__(self, plugins_dir: Path = Path("plugins")):
        self._plugins_dir = plugins_dir
        self._registry: Dict[str, type] = {}
        self._loaded = False

    def load(self, bus: Optional[EventBus] = None) -> None:
        if self._loaded:
            return
        
        if not self._plugins_dir.exists():
            logger.warning(f"Plugins directory not found: {self._plugins_dir}")
            self._loaded = True
            return

        # Walk plugins_dir to max_depth=2.
        # Depth 1: plugins/*.py
        # Depth 2: plugins/*/*.py
        # Exclude __init__.py
        files = list(self._plugins_dir.glob("*.py")) + list(self._plugins_dir.glob("*/*.py"))
        
        for file_path in files:
            if file_path.name == "__init__.py":
                continue
            
            try:
                # Use a unique module name
                module_name = f"nexus_plugin_{uuid.uuid4().hex}"
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Inspect every class
                    for _, cls in inspect.getmembers(module, inspect.isclass):
                        if issubclass(cls, BaseScanner) and cls is not BaseScanner:
                            # Skip internal
                            if getattr(cls, 'is_internal', False):
                                continue
                                
                            # Validate
                            errors = validate_scanner_class(cls)
                            if errors:
                                for error in errors:
                                    logger.warning(f"Plugin validation failed for {cls.__name__} in {file_path}: {error}")
                                continue
                            
                            # Duplicate check
                            scanner_name = getattr(cls, 'name')
                            if scanner_name in self._registry:
                                logger.warning(f"Duplicate scanner name found: {scanner_name}. Skipping {cls.__name__}")
                                continue
                                
                            self._registry[scanner_name] = cls
                            
            except Exception as e:
                msg = f"Failed to load plugin from {file_path}: {e}"
                if bus:
                    try:
                        import asyncio
                        loop = asyncio.get_running_loop()
                        loop.create_task(bus.publish_log("WARNING", msg))
                    except RuntimeError:
                        logger.warning(msg)
                else:
                    logger.warning(msg)
        
        self._loaded = True
        
    def reload(self) -> None:
        self._registry = {}
        self._loaded = False
        self.load()

    def get(self, name: str) -> Optional[type]:
        return self._registry.get(name)

    def all(self) -> List[type]:
        return list(self._registry.values())

    def names(self) -> List[str]:
        return list(self._registry.keys())

    def instantiate(self, name: str, config: Dict, bus: EventBus) -> BaseScanner:
        if name not in self._registry:
            raise KeyError(f"Scanner '{name}' not registered")
        cls = self._registry[name]
        return cls(config=config, bus=bus)
