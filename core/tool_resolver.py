# core/tool_resolver.py
"""
Utilities for checking whether external scanner tools are available
on the current system.

Provides both sync (is_tool_available) and async (is_tool_available_async)
variants. The async variant should be used in API handlers to avoid blocking
the aiohttp event loop.
"""

from __future__ import annotations
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.python_exe import _get_venv_python


def is_tool_available(tool_name: str) -> bool:
    """
    Return True if `tool_name` is executable on the current system.
    Sync version — do NOT call from async handlers; use is_tool_available_async().
    """
    venv_python = _get_venv_python()
    if venv_python:
        bin_dir = venv_python.parent
        candidates = [bin_dir / tool_name, bin_dir / f"{tool_name}.exe"]
        if any(p.exists() for p in candidates):
            return True

    if shutil.which(tool_name):
        return True

    if venv_python and venv_python.exists():
        try:
            r = subprocess.run(
                [str(venv_python), "-c", f"import {tool_name}"],
                capture_output=True, timeout=3,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass

    try:
        r = subprocess.run(
            [sys.executable, "-c", f"import {tool_name}"],
            capture_output=True, timeout=3,
        )
        if r.returncode == 0:
            return True
    except Exception:
        pass

    return False


async def is_tool_available_async(tool_name: str) -> bool:
    """
    Async version of is_tool_available — does NOT block the event loop.
    Uses asyncio.create_subprocess_exec instead of subprocess.run.
    """
    # 1. Venv bin directory (sync path check — cheap, no subprocess)
    venv_python = _get_venv_python()
    if venv_python:
        bin_dir = venv_python.parent
        candidates = [bin_dir / tool_name, bin_dir / f"{tool_name}.exe"]
        if any(p.exists() for p in candidates):
            return True

    # 2. System PATH (shutil.which is a pure stdlib call, safe to call sync)
    if shutil.which(tool_name):
        return True

    # 3. Try running with --version to confirm executable works
    try:
        proc = await asyncio.create_subprocess_exec(
            tool_name, "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return proc.returncode == 0
    except Exception:
        pass

    return False


async def get_tool_version_async(tool_name: str) -> Optional[str]:
    """
    Async version of get_tool_version.
    """
    for flag in ("--version", "-V"):
        try:
            cmd = shutil.which(tool_name) or tool_name
            proc = await asyncio.create_subprocess_exec(
                cmd, flag,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            out = (stdout or stderr or b"").decode(errors="replace").strip()
            if out:
                return out.splitlines()[0]
        except Exception:
            continue
    return None


def get_tool_version(tool_name: str) -> Optional[str]:
    """
    Try to retrieve the installed version of a tool (sync).
    Returns the version string or None if unavailable.
    """
    for flag in ("--version", "-V", "version"):
        try:
            cmd = shutil.which(tool_name) or tool_name
            r = subprocess.run(
                [cmd, flag],
                capture_output=True,
                timeout=5,
                text=True,
            )
            out = (r.stdout or r.stderr or "").strip()
            if out:
                return out.splitlines()[0]
        except Exception:
            continue
    return None


# Canonical pip package name for each scanner tool
TOOL_PIP_PACKAGE: dict[str, str] = {
    "vulture":         "vulture",
    "bandit":          "bandit",
    "radon":           "radon",
    "pylint":          "pylint",
    "semgrep":         "semgrep",
    "pip-audit":       "pip-audit",
    "lizard":          "lizard",
}
