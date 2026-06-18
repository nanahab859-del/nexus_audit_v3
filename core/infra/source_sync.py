import asyncio
import os
import shutil
import tempfile
import uuid
import fnmatch
import logging
from urllib.parse import urlparse
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
        token = os.environ.get(config.token_env) if config.token_env else None

        masked_url = url
        if bus:
            await bus.publish_log("info", f"Cloning {masked_url}...")

        if token:
            await _clone_with_token(url, token, wd)
        else:
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
            except SyncError:
                raise
            except Exception as e:
                raise SyncError(f"Clone failed: {e}")

        return wd

    else:
        raise SyncError(f"Unknown source_type: {config.source_type}")


async def _clone_with_token(url: str, token: str, dest: Path) -> None:
    """Clone a private repo using a temporary credential file (token never in process list)."""
    parsed = urlparse(url)
    cred_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".creds", delete=False
        ) as cf:
            cf.write(f"https://oauth2:{token}@{parsed.netloc}\n")
            cred_path = cf.name
        os.chmod(cred_path, 0o600)

        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": f"store --file={cred_path}",
        }
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", url, str(dest),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise SyncError(stderr.decode(errors="replace").strip())
    except SyncError:
        raise
    except asyncio.TimeoutError:
        raise SyncError("Clone timed out after 120 seconds")
    except Exception as e:
        raise SyncError(str(e))
    finally:
        if cred_path:
            try:
                os.unlink(cred_path)   # always delete — even on failure
            except OSError:
                pass
