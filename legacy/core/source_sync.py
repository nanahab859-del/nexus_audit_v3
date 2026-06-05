import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.events import EventBus

@dataclass
class SyncConfig:
    enabled: bool = False
    sync_dir: Optional[Path] = None
    backup_dir: Optional[Path] = None
    exclude: list[str] | None = None

    def __post_init__(self) -> None:
        if self.exclude is None:
            self.exclude = [
                ".git", ".venv", "venv", "__pycache__", "*.pyc",
                "node_modules", ".env", "*.log"
            ]

def _parse_sync_config(raw_config: dict[str, Any] | None, project_path: Path) -> SyncConfig:
    raw_config = raw_config or {}
    sync_data = raw_config.get("source_sync", {})
    
    enabled = sync_data.get("enabled", False)
    
    source_path_str = sync_data.get("source_path")
    source_path = Path(source_path_str) if source_path_str else project_path
    
    working_path_str = sync_data.get("working_path")
    working_path = Path(working_path_str) if working_path_str else None
    
    exclude = sync_data.get("exclude")
    
    return SyncConfig(
        enabled=enabled,
        sync_dir=source_path,
        backup_dir=working_path,
        exclude=exclude
    )

async def sync(raw_config: dict[str, Any] | None, project_path: Path, bus: EventBus) -> Path:
    """
    If enabled: copy source → working_path, return working_path.
    If disabled: return project_path from Settings.
    """
    config = _parse_sync_config(raw_config, project_path)
    
    if not config.enabled or not config.backup_dir:
        return project_path
        
    await bus.publish_log("info", f"Syncing source to {config.backup_dir}...")
    await bus.publish_progress("source_sync", 0, "Starting copy...")
    
    def _do_copy() -> None:
        if config.backup_dir is None or config.sync_dir is None:
            return
        if config.backup_dir.exists():
            shutil.rmtree(config.backup_dir, ignore_errors=True)
            
        # Strip trailing slashes from excludes for ignore_patterns
        clean_excludes = [p.rstrip("/") for p in (config.exclude or [])]
        ignore = shutil.ignore_patterns(*clean_excludes)
        
        shutil.copytree(
            config.sync_dir,
            config.backup_dir,
            ignore=ignore,
            dirs_exist_ok=True
        )
        
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _do_copy)
    
    await bus.publish_progress("source_sync", 100, "Copy complete")
    await bus.publish_log("info", f"Source sync complete.")
    
    return config.backup_dir
