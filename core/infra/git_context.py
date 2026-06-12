import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

async def _run_git(project_path: Path, *args: str) -> Optional[str]:
    """Helper to run git commands asynchronously."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(project_path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except asyncio.TimeoutError:
            try:
                proc.terminate()
                await proc.wait()  # Clean up zombie process
            except Exception:
                pass
            logger.warning(f"Git command timed out: git {' '.join(args)}")
            return None
            
        if proc.returncode != 0:
            # Silently debug or log warning without breaking the flow
            logger.debug(f"Git command exited with {proc.returncode}: git {' '.join(args)}")
            return None
            
        return stdout.decode().strip()
    except FileNotFoundError:
        logger.warning("Git binary not found on this system. Skipping Git context extraction.")
        return None
    except Exception as e:
        logger.warning(f"Git execution error: {e}")
        return None

def _convert_ssh_to_https(remote_url: str) -> str:
    """Convert git@host:path.git to https://host/path"""
    pattern = r"git@([^:]+):(.+)\.git"
    match = re.match(pattern, remote_url)
    if match:
        return f"https://{match.group(1)}/{match.group(2)}"
    return remote_url

async def get_git_context(project_path: Path) -> dict:
    """Extract Git metadata from a project directory."""
    remote_raw = await _run_git(project_path, "remote", "get-url", "origin")
    remote_url = None
    if remote_raw:
        remote_url = _convert_ssh_to_https(remote_raw)
    
    branch = await _run_git(project_path, "branch", "--show-current")
    if branch == "":
        branch = None
        
    log_output = await _run_git(project_path, "log", "-1", "--format=%H|%an|%aI")
    commit, author, commit_timestamp = None, None, None
    if log_output:
        parts = log_output.split("|")
        if len(parts) >= 1: commit = parts[0]
        if len(parts) >= 2: author = parts[1]
        if len(parts) >= 3: commit_timestamp = parts[2]
        
    # Return standard contract structure even if fields are None
    if not any([remote_raw, branch, commit]):
        return {}
        
    return {
        "remote_url": remote_url,
        "raw_remote_url": remote_raw,
        "branch": branch,
        "commit": commit,
        "author": author,
        "commit_timestamp": commit_timestamp,
    }
