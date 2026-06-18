import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from core.infra.git_utils import run_git as _run_git

async def get_changed_files(project_path: Path) -> Optional[list[Path]]:
    """
    Return a list of files changed since the last commit.
    """
    # 2. Verify HEAD exists (if no commits, force full scan)
    head = await _run_git(["rev-parse", "--verify", "HEAD"], cwd=project_path)
    if head is None:
        return None

    # 3. Get Git root directory
    root_str = await _run_git(["rev-parse", "--show-toplevel"], cwd=project_path)
    if root_str is None:
        return None
    git_root = Path(root_str).resolve()

    # 4. Get changed tracked files
    diff_output = await _run_git(["diff", "--name-only", "HEAD"], cwd=project_path)
    tracked = diff_output.splitlines() if diff_output else []

    # 5. Get untracked files
    untracked_output = await _run_git(["ls-files", "--others", "--exclude-standard"], cwd=project_path)
    untracked = untracked_output.splitlines() if untracked_output else []

    # 6. Combine and normalize
    all_relative = tracked + untracked
    if not all_relative:
        return []
        
    return [git_root / rel_path for rel_path in all_relative if rel_path.strip()]
