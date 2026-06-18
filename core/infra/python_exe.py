import sys
import os
from pathlib import Path
from typing import Optional

def get_venv_python() -> Optional[Path]:
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    if sys.platform == "win32":
        candidates = ["python.exe", "python3.exe"]
    else:
        candidates = ["python3", "python"]   # python3 preferred; python as fallback

    # 1. Check VIRTUAL_ENV
    venv_root = os.environ.get("VIRTUAL_ENV")
    if venv_root:
        for name in candidates:
            candidate = Path(venv_root) / bin_dir / name
            if candidate.exists():
                return candidate
    # 2. Check CWD/.venv
    local_venv = Path.cwd() / ".venv"
    if local_venv.exists():
        for name in candidates:
            candidate = local_venv / bin_dir / name
            if candidate.exists():
                return candidate
    return None

def get_python_for_tools() -> Path:
    venv = get_venv_python()
    if venv:
        return venv
    return Path(sys.executable)
