import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

def _get_venv_python() -> Optional[Path]:
    r"""
    Find the Python executable inside the project's virtualenv.
    
    Checks in order:
    1. VIRTUAL_ENV environment variable (if venv is active)
    2. Local .venv directory in project
    3. Returns None if not found
    
    Cross-platform: handles both .venv/bin/python3 (POSIX) 
    and .venv\Scripts\python.exe (Windows)
    """
    # Step 1: Check VIRTUAL_ENV (set when venv is active)
    venv_root = os.environ.get("VIRTUAL_ENV")
    if venv_root:
        return _python_from_venv(Path(venv_root))
    
    # Step 2: Check local .venv directory
    local_venv = Path.cwd() / ".venv"
    if local_venv.exists():
        return _python_from_venv(local_venv)
    
    return None

def _python_from_venv(venv: Path) -> Path:
    """Get Python executable path for given venv root."""
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    else:
        return venv / "bin" / "python3"

def find_tool_command(tool_name: str) -> str:
    """
    Find a tool command in PATH. Prioritize virtualenv.
    
    Strategy:
    1. Try to find tool in venv's bin (or Scripts on Windows)
    2. Try to find tool in system PATH
    3. For pure-Python tools, check if importable in venv/global Python
    
    Args:
        tool_name: Name of tool (e.g., "vulture", "bandit", "semgrep")
    
    Returns:
        Path to tool executable (as string)
    
    Raises:
        FileNotFoundError: If tool not found anywhere
    """
    # Priority 1: Check venv's bin/Scripts directory
    venv_python = _get_venv_python()
    if venv_python:
        bin_dir = venv_python.parent
        if sys.platform == "win32":
            tool_path = bin_dir / f"{tool_name}.exe"
        else:
            tool_path = bin_dir / tool_name
        
        if tool_path.exists():
            return str(tool_path)
    
    # Priority 2: Check system PATH
    tool_path = shutil.which(tool_name)
    if tool_path:
        return tool_path
    
    # Priority 3: For pure-Python tools, check if importable in venv Python
    if venv_python:
        try:
            result = subprocess.run(
                [str(venv_python), "-c", f"import {tool_name}"],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                # Tool is a Python module; run via "python -m tool"
                return f"{venv_python} -m"
        except Exception:
            pass
    
    # Priority 4: Check system Python for pure-Python tools
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {tool_name}"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return f"{sys.executable} -m"
    except Exception:
        pass
    
    # Tool not found anywhere
    raise FileNotFoundError(
        f"Tool '{tool_name}' not found in PATH or installed Python.\n"
        f"Install with: pip install {tool_name}"
    )
