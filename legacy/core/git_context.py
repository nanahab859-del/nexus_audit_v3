from typing import Any
import asyncio
from pathlib import Path
import re

async def get_git_context(project_path: Path) -> dict[str, Any]:
    """
    Returns {"remote_url": str, "branch": str, "commit": str}
    SSH remotes converted to HTTPS. Returns {} silently on any failure.
    """
    try:
        # Check if git exists
        proc = await asyncio.create_subprocess_exec(
            "git", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        await proc.communicate()
        if proc.returncode != 0:
            return {}

        # Get commit
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {}
        commit = stdout.decode().strip()

        # Get branch
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--abbrev-ref", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {}
        branch = stdout.decode().strip()
        if branch == "HEAD":
            # Might be detached, try getting branch from reflog or another way, or just leave it empty
            branch = ""

        # Get remote URL
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "--get", "remote.origin.url",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        stdout, _ = await proc.communicate()
        remote_url = stdout.decode().strip()
        
        # Convert SSH to HTTPS
        if remote_url.startswith("git@"):
            # git@github.com:user/repo.git -> https://github.com/user/repo.git
            remote_url = re.sub(r"^git@([^:]+):", r"https://\1/", remote_url)

        return {
            "remote_url": remote_url,
            "branch": branch,
            "commit": commit
        }
    except Exception:
        return {}
