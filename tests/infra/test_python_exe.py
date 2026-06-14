import pytest
import os
import sys
from pathlib import Path
from core.infra.python_exe import get_venv_python, get_python_for_tools

def test_get_venv_python_from_env(tmp_path, monkeypatch):
    venv_dir = tmp_path / "env"
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    python_bin = venv_dir / bin_dir
    python_bin.mkdir(parents=True)
    exe_name = "python.exe" if sys.platform == "win32" else "python3"
    (python_bin / exe_name).touch()
    
    monkeypatch.setenv("VIRTUAL_ENV", str(venv_dir))
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path) # prevent cwd fallback finding it
    assert get_venv_python() == python_bin / exe_name

def test_get_venv_python_from_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    
    venv_dir = tmp_path / ".venv"
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    python_bin = venv_dir / bin_dir
    python_bin.mkdir(parents=True)
    exe_name = "python.exe" if sys.platform == "win32" else "python3"
    (python_bin / exe_name).touch()
    
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    assert get_venv_python() == python_bin / exe_name

def test_get_venv_python_none(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    assert get_venv_python() is None

def test_get_python_for_tools_venv(monkeypatch, tmp_path):
    monkeypatch.setattr("core.infra.python_exe.get_venv_python", lambda: Path("/fake/python"))
    assert get_python_for_tools() == Path("/fake/python")

def test_get_python_for_tools_system(monkeypatch):
    monkeypatch.setattr("core.infra.python_exe.get_venv_python", lambda: None)
    assert get_python_for_tools() == Path(sys.executable)
