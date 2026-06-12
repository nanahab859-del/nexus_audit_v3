import asyncio
import logging
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
                await proc.wait()
            except Exception:
                pass
            logger.warning(f"Git command timed out: git {' '.join(args)}")
            return None
            
        if proc.returncode != 0:
            logger.debug(f"Git command failed (exit {proc.returncode}): git {' '.join(args)}")
            return None
            
        return stdout.decode().strip()
    except Exception as e:
        logger.warning(f"Git execution error: {e}")
        return None

async def get_changed_files(project_path: Path) -> Optional[list[Path]]:
    """
    Return a list of files changed since the last commit.
    """
    # 2. Verify HEAD exists (if no commits, force full scan)
    head = await _run_git(project_path, "rev-parse", "--verify", "HEAD")
    if head is None:
        return None

    # 3. Get Git root directory
    root_str = await _run_git(project_path, "rev-parse", "--show-toplevel")
    if root_str is None:
        return None
    git_root = Path(root_str).resolve()

    # 4. Get changed tracked files
    diff_output = await _run_git(project_path, "diff", "--name-only", "HEAD")
    tracked = diff_output.splitlines() if diff_output else []

    # 5. Get untracked files
    untracked_output = await _run_git(project_path, "ls-files", "--others", "--exclude-standard")
    untracked = untracked_output.splitlines() if untracked_output else []

    # 6. Combine and normalize
    all_relative = tracked + untracked
    if not all_relative:
        return []
        
    return [git_root / rel_path for rel_path in all_relative if rel_path.strip()]
