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

    async def is_available(self, tool_name: str) -> bool:
        try:
            await self.resolve(tool_name)
            return True
        except ToolNotFoundError:
            return False

    async def resolve(self, tool_name: str) -> List[str]:
        # 1. Cache check
        if tool_name in self._resolved:
            cached = self._resolved[tool_name]
            if cached is None:
                raise ToolNotFoundError(f"{tool_name} not found. Install with: pip install {tool_name}")
            return cached

        # 2. Venv bin directory
        venv_python = get_venv_python()
        if venv_python:
            bin_dir = venv_python.parent
            exe_name = f"{tool_name}.exe" if sys.platform == "win32" else tool_name
            candidate = bin_dir / exe_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                result = [str(candidate)]
                self._resolved[tool_name] = result
                return result

        # 3. System PATH
        found = shutil.which(tool_name)
        if found:
            result = [found]
            self._resolved[tool_name] = result
            return result

        # 4. Python module fallback
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
                self._resolved[tool_name] = result
                return result
        except (asyncio.TimeoutError, Exception):
            pass

        # 5. Not found
        self._resolved[tool_name] = None
        raise ToolNotFoundError(f"{tool_name} not found. Install with: pip install {tool_name}")
