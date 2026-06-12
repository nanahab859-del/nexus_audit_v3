import sys
import os
from pathlib import Path
from typing import Optional

def get_venv_python() -> Optional[Path]:
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    # 1. Check VIRTUAL_ENV
    venv_root = os.environ.get("VIRTUAL_ENV")
    if venv_root:
        candidate = Path(venv_root) / bin_dir / ("python.exe" if sys.platform == "win32" else "python3")
        if candidate.exists():
            return candidate
    # 2. Check CWD/.venv
    local_venv = Path.cwd() / ".venv"
    if local_venv.exists():
        candidate = local_venv / bin_dir / ("python.exe" if sys.platform == "win32" else "python3")
        if candidate.exists():
            return candidate
    return None

def get_python_for_tools() -> Path:
    venv = get_venv_python()
    if venv:
        return venv
    return Path(sys.executable)
