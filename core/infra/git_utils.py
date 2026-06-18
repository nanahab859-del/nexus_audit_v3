"""Shared git subprocess helper. Import run_git from here — never duplicate."""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
GIT_TIMEOUT = 30


async def run_git(
    args: list[str],
    cwd: Optional[Path] = None,
    timeout: float = GIT_TIMEOUT,
) -> Optional[str]:
    """Run a git command. Returns stdout string or None on any failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            logger.debug("git %s exited %d", " ".join(args), proc.returncode)
            return None
        return stdout.decode(errors="replace").strip()
    except FileNotFoundError:
        logger.debug("git binary not found")
        return None
    except asyncio.TimeoutError:
        logger.warning("git %s timed out after %ss", " ".join(args), timeout)
        return None
    except Exception as e:
        logger.warning("git %s failed: %s", " ".join(args), e)
        return None
