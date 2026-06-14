import asyncio
import os
import sys
import shutil
from pathlib import Path
from typing import Optional, List
from core.infra.python_exe import get_venv_python, get_python_for_tools

class ToolNotFoundError(Exception):
    pass

class ToolResolver:
    def __init__(self):
        self._resolved: dict[str, Optional[List[str]]] = {}

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
            cached = self._resolved[cache_key]
            if cached is None:
                raise ToolNotFoundError(f"{tool_name} not found in {ecosystem}.")
            return cached

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
            self._resolved[cache_key] = None
            raise ToolNotFoundError(f"{tool_name} not found in node_modules or system path.")

        # 3. Binary ecosystem (System PATH only)
        if ecosystem == "binary":
            found = shutil.which(tool_name)
            if found:
                result = [found]
                self._resolved[cache_key] = result
                return result
            self._resolved[cache_key] = None
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
        self._resolved[cache_key] = None
        raise ToolNotFoundError(f"{tool_name} not found in python environment.")
