import asyncio
from pathlib import Path

async def get_changed_files(project_path: Path) -> list[Path] | None:
    """
    Returns files changed since last commit via git diff.
    Includes unstaged, staged, and untracked files.
    Returns None if git unavailable or not a git repository.
    """
    try:
        # Check if it's a git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--is-inside-work-tree",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        await proc.communicate()
        if proc.returncode != 0:
            return None

        changed_files = set()

        # 1. Tracked changed files (both staged and unstaged)
        # Using HEAD to compare against the last commit
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            for line in stdout.decode().strip().split("\n"):
                if line:
                    changed_files.add(project_path / line)

        # 2. Untracked files
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-files", "--others", "--exclude-standard",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            for line in stdout.decode().strip().split("\n"):
                if line:
                    changed_files.add(project_path / line)

        return list(changed_files)
    except Exception:
        return None
