import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from core.infra.git_utils import run_git as _run_git

def _convert_ssh_to_https(remote_url: str) -> str:
    """Convert git@host:path.git to https://host/path"""
    pattern = r"git@([^:]+):(.+)\.git"
    match = re.match(pattern, remote_url)
    if match:
        return f"https://{match.group(1)}/{match.group(2)}"
    return remote_url

async def get_git_context(project_path: Path) -> dict:
    """Extract Git metadata from a project directory."""
    remote_raw = await _run_git(["remote", "get-url", "origin"], cwd=project_path)
    remote_url = None
    if remote_raw:
        remote_url = _convert_ssh_to_https(remote_raw)
    
    branch = await _run_git(["branch", "--show-current"], cwd=project_path)
    if branch == "":
        branch = None
        
    log_output = await _run_git(["log", "-1", "--format=%H|%an|%aI"], cwd=project_path)
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
