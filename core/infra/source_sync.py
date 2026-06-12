import asyncio
import os
import shutil
import tempfile
import uuid
import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from core.primitives.events import EventBus
from core.primitives.atomic import write_json  # Included as requested by prompt

@dataclass
class SyncConfig:
    enabled: bool = False
    source_type: str = "local"      # "local" | "remote"
    local_path: str = ""
    remote_url: str = ""
    remote_branch: str = "main"
    token_env: str = ""             # env var name, e.g. "GIT_TOKEN"
    working_dir: str = ""           # leave empty to use system temp
    exclude_patterns: list[str] = field(default_factory=lambda: [
        ".git", ".venv", "__pycache__", "node_modules"
    ])

class SyncError(Exception):
    """Raised when source sync fails."""
    pass

def _inject_token(url: str, token: str) -> str:
    # https://github.com/user/repo.git -> https://x-access-token:token@github.com/user/repo.git
    # Simple replacement assuming github/gitlab style
    import re
    return re.sub(r'https://([^/]+)/', f'https://x-access-token:{token}@\\1/', url)

def _mask_token(text: str) -> str:
    import re
    return re.sub(r'x-access-token:[^@]+', 'x-access-token:***', text)

async def sync(config: SyncConfig, bus: Optional[EventBus] = None) -> Path:
    """
    Prepare the working directory for an audit.
    Returns the absolute path to the working directory.
    """
    if not config.enabled:
        return Path(config.local_path)
    
    # 2. Determine working_dir
    if config.working_dir:
        wd = Path(config.working_dir)
    else:
        wd = Path(tempfile.gettempdir()) / f"nexus-audit-{uuid.uuid4().hex[:12]}"
    wd.mkdir(parents=True, exist_ok=True)
    
    # 3. Local sync
    if config.source_type == "local":
        if bus:
            await bus.publish_log("info", "Copying local files...")
        
        def _ignore(dir, names):
            return [n for n in names if any(fnmatch.fnmatch(n, p) for p in config.exclude_patterns)]
        
        await asyncio.to_thread(shutil.copytree, Path(config.local_path), wd,
                                ignore=_ignore, dirs_exist_ok=True)
        return wd
        
    # 4. Remote sync
    elif config.source_type == "remote":
        if not config.remote_url:
            raise SyncError("Remote URL is required")
        
        url = config.remote_url
        if config.token_env:
            token = os.environ.get(config.token_env)
            if token:
                url = _inject_token(url, token)
        
        masked_url = _mask_token(url)
        if bus:
            await bus.publish_log("info", f"Cloning {masked_url}...")
            
        cmd = ["git", "clone", "--depth", "1", "--branch", config.remote_branch, url, str(wd)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            
            if proc.returncode != 0:
                raise SyncError(f"Clone failed: {stderr.decode().strip()[:500]}")
        except asyncio.TimeoutError:
            raise SyncError("Clone timed out after 120 seconds")
        except Exception as e:
            raise SyncError(f"Clone failed: {_mask_token(str(e))}")
        
        return wd
        
    else:
        raise SyncError(f"Unknown source_type: {config.source_type}")
