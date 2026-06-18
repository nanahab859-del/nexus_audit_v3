import asyncio
import os
import sys
import shutil
from pathlib import Path
from time import monotonic
from typing import Optional, List
from core.infra.python_exe import get_venv_python, get_python_for_tools

class ToolNotFoundError(Exception):
    pass

class ToolResolver:
    _NOT_FOUND_TTL = 300   # 5 minutes

    def __init__(self):
        self._resolved: dict[str, Optional[List[str]]] = {}   # successes (permanent)
        self._not_found: dict[str, float] = {}                # failures with TTL (monotonic timestamps)

    async def is_available(self, tool_name: str, ecosystem: str = "python") -> bool:
        try:
            await self.resolve(tool_name, ecosystem)
            return True
        except ToolNotFoundError:
            return False

    async def resolve(self, tool_name: str, ecosystem: str = "python") -> List[str]:
        # 1. Cache check
        cache_key = f"{ecosystem}:{tool_name}"
        if cache_key in self._resolved:
            return self._resolved[cache_key]

        # Negative cache with TTL
        if cache_key in self._not_found:
            if monotonic() - self._not_found[cache_key] < self._NOT_FOUND_TTL:
                raise ToolNotFoundError(f"{tool_name} not found in {ecosystem}.")
            del self._not_found[cache_key]   # TTL expired — retry

        # 2. Node ecosystem
        if ecosystem == "node":
            # Check local project node_modules
            local_eslint = Path("node_modules") / ".bin" / tool_name
            if local_eslint.is_file() and os.access(local_eslint, os.X_OK):
                result = [str(local_eslint)]
                self._resolved[cache_key] = result
                return result
            # Fallback to system
            found = shutil.which(tool_name)
            if found:
                result = [found]
                self._resolved[cache_key] = result
                return result
            self._not_found[cache_key] = monotonic()
            raise ToolNotFoundError(f"{tool_name} not found in node_modules or system path.")

        # 3. Binary ecosystem (System PATH only)
        if ecosystem == "binary":
            found = shutil.which(tool_name)
            if found:
                result = [found]
                self._resolved[cache_key] = result
                return result
            self._not_found[cache_key] = monotonic()
            raise ToolNotFoundError(f"{tool_name} not found in system path.")

        # 4. Python ecosystem (default)
        # Venv bin directory
        venv_python = get_venv_python()
        if venv_python:
            bin_dir = venv_python.parent
            exe_name = f"{tool_name}.exe" if sys.platform == "win32" else tool_name
            candidate = bin_dir / exe_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                result = [str(candidate)]
                self._resolved[cache_key] = result
                return result

        # System PATH
        found = shutil.which(tool_name)
        if found:
            result = [found]
            self._resolved[cache_key] = result
            return result

        # Python module fallback
        python_path = str(get_python_for_tools())
        try:
            proc = await asyncio.create_subprocess_exec(
                python_path, "-c", f"import {tool_name}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                result = [python_path, "-m", tool_name]
                self._resolved[cache_key] = result
                return result
        except (asyncio.TimeoutError, Exception):
            pass

        # Not found
        self._not_found[cache_key] = monotonic()
        raise ToolNotFoundError(f"{tool_name} not found in python environment.")

    def clear_cache(self) -> None:
        """Force re-resolution of all tools. Call after installing a scanner."""
        self._resolved.clear()
        self._not_found.clear()


# ── Module-level helpers (imported by routes_config) ─────────────────────────

TOOL_PIP_PACKAGE: dict = {
    "bandit":    "bandit",
    "ruff":      "ruff",
    "mypy":      "mypy",
    "vulture":   "vulture",
    "radon":     "radon",
    "pylint":    "pylint",
    "semgrep":   "semgrep",
    "pip_audit": "pip-audit",
    "lizard":    "lizard",
    "djlint":    "djlint",
    "trufflehog":"trufflehog",
    "eslint":    "eslint",
}


def is_tool_available(tool_name: str) -> bool:
    return shutil.which(tool_name) is not None


def get_tool_version(tool_name: str) -> str | None:
    import subprocess
    try:
        r = subprocess.run(
            [tool_name, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return (r.stdout or r.stderr or "").strip().splitlines()[0] or None
    except Exception:
        return None


async def is_tool_available_async(tool_name: str) -> bool:
    return await asyncio.to_thread(is_tool_available, tool_name)


async def get_tool_version_async(tool_name: str) -> str | None:
    return await asyncio.to_thread(get_tool_version, tool_name)
