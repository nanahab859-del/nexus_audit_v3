# api/routes_project.py
"""
Project-specific endpoints:
  POST /api/project/ping            — validate path, auto-detect metadata
  POST /api/project/validate-remote — check remote repo reachability
"""

from __future__ import annotations
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

from aiohttp import web


async def ping_project(request: web.Request) -> web.Response:
    """
    Validate a local path and extract project metadata.
    Called when the developer enters a path and clicks Ping Project.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    raw_path = (body.get("path") or "").strip()
    if not raw_path:
        return web.json_response({"valid": False, "error": "path is required"}, status=400)

    path = Path(raw_path).expanduser().resolve()

    if not path.exists():
        return web.json_response({"valid": False, "error": f"Path does not exist: {path}"})
    if not path.is_dir():
        return web.json_response({"valid": False, "error": f"Path is not a directory: {path}"})

    result: dict[str, Any] = {
        "valid": True,
        "path": str(path),
        "project_name": path.name,
        "project_key":  _to_slug(path.name),
        "project_version": "",
        "primary_stack": [],
        "git_remote": "",
        "git_branch": "",
        "suggested_exclusions": [],
        "suggested_extensions": [],
        "suggested_test_pattern": "",
        "framework_hints": [],
    }

    # ── Version detection ────────────────────────────────────────────────────
    result["project_version"] = _detect_version(path)

    # ── Stack + extension detection ──────────────────────────────────────────
    stacks, extensions, test_pattern, frameworks = _detect_stack(path)
    result["primary_stack"]           = stacks
    result["suggested_extensions"]    = extensions
    result["suggested_test_pattern"]  = test_pattern
    result["framework_hints"]         = frameworks

    # ── Scope defaults based on stack ────────────────────────────────────────
    exclusions = ["**/__pycache__/**", "**/*.pyc"]
    if "javascript" in stacks or "typescript" in stacks:
        exclusions.append("node_modules/**")
    if path.joinpath(".venv").exists() or path.joinpath("venv").exists():
        exclusions.append(".venv/**")
    if path.joinpath("migrations").exists():
        exclusions.append("migrations/**")
    result["suggested_exclusions"] = exclusions

    # ── Git metadata ─────────────────────────────────────────────────────────
    git_dir = path / ".git"
    if git_dir.exists():
        result["git_remote"] = await _git_remote(path)
        result["git_branch"] = await _git_branch(path)

    return web.json_response(result)


async def validate_remote(request: web.Request) -> web.Response:
    """
    Check whether a remote Git repository is reachable.
    Does NOT clone. Uses `git ls-remote` with a 10-second timeout.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    url  = (body.get("url") or "").strip()
    if not url:
        return web.json_response({"reachable": False, "error": "url is required"}, status=400)

    env_var  = (body.get("token_env") or "").strip()
    import os, tempfile
    env = os.environ.copy()

    cred_path = None
    url_to_use = url

    if env_var and env_var in os.environ:
        token = os.environ[env_var]
        if token and url.startswith("https://"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".creds", delete=False
            ) as cf:
                cf.write(f"https://oauth2:{token}@{parsed.netloc}\n")
                cred_path = cf.name
            os.chmod(cred_path, 0o600)
            env["GIT_CONFIG_COUNT"]   = "1"
            env["GIT_CONFIG_KEY_0"]   = "credential.helper"
            env["GIT_CONFIG_VALUE_0"] = f"store --file={cred_path}"

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--quiet", "--exit-code", url_to_use, "HEAD",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode == 0:
            return web.json_response({"reachable": True})
        err = (stderr or b"").decode(errors="replace").strip()
        return web.json_response({"reachable": False, "error": err or "Repository not reachable"})
    except asyncio.TimeoutError:
        return web.json_response({"reachable": False, "error": "Connection timed out (10s)"})
    except Exception as e:
        return web.json_response({"reachable": False, "error": str(e)})
    finally:
        if cred_path and os.path.exists(cred_path):
            os.unlink(cred_path)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def _detect_version(path: Path) -> str:
    """Try to read the project version from standard manifest files."""
    # pyproject.toml
    pp = path / "pyproject.toml"
    if pp.exists():
        try:
            import tomllib
            with open(pp, "rb") as f:
                data = tomllib.load(f)
            v = (data.get("project") or data.get("tool", {}).get("poetry", {})).get("version","")
            if v: return v
        except Exception:
            pass
    # package.json
    pj = path / "package.json"
    if pj.exists():
        try:
            import json
            data = json.loads(pj.read_text())
            if data.get("version"): return data["version"]
        except Exception:
            pass
    # setup.py (crude)
    sp = path / "setup.py"
    if sp.exists():
        try:
            text = sp.read_text()
            m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
            if m: return m.group(1)
        except Exception:
            pass
    # Cargo.toml
    ct = path / "Cargo.toml"
    if ct.exists():
        try:
            import tomllib
            with open(ct, "rb") as f:
                data = tomllib.load(f)
            v = data.get("package", {}).get("version", "")
            if v: return v
        except Exception:
            pass
    return ""


_STACK_MARKERS: list[tuple[str, list[str], list[str], str, list[str]]] = [
    # (stack_name, marker_files, extensions, test_pattern, frameworks)
    ("python",     ["pyproject.toml","setup.py","requirements.txt","Pipfile"],
                   [".py"], "test_*.py", []),
    ("javascript", ["package.json"],
                   [".js",".jsx"], "*.test.js", []),
    ("typescript", ["tsconfig.json"],
                   [".ts",".tsx"], "*.spec.ts", []),
    ("go",         ["go.mod"],
                   [".go"], "*_test.go", []),
    ("rust",       ["Cargo.toml"],
                   [".rs"], "*_test.rs", []),
    ("java",       ["pom.xml","build.gradle"],
                   [".java"], "*Test.java", []),
    ("ruby",       ["Gemfile"],
                   [".rb"], "*_spec.rb", []),
]

_FRAMEWORK_MARKERS = {
    "django":    "django",
    "flask":     "flask",
    "fastapi":   "fastapi",
    "react":     "react",
    "vue":       "vue",
    "next":      "next",
    "express":   "express",
    "rails":     "rails",
}


def _detect_stack(path: Path) -> tuple[list[str], list[str], str, list[str]]:
    stacks: list[str]     = []
    extensions: list[str] = []
    test_pattern          = ""
    frameworks: list[str] = []

    for stack, markers, exts, pattern, _ in _STACK_MARKERS:
        if any((path / m).exists() for m in markers):
            stacks.append(stack)
            extensions.extend(e for e in exts if e not in extensions)
            if not test_pattern:
                test_pattern = pattern

    # Framework hints from dependency files
    dep_files = ["requirements.txt", "Pipfile", "pyproject.toml", "package.json"]
    combined_text = ""
    for f in dep_files:
        fp = path / f
        if fp.exists():
            try:
                combined_text += fp.read_text(errors="replace").lower()
            except Exception:
                pass

    for fw, keyword in _FRAMEWORK_MARKERS.items():
        if keyword in combined_text:
            frameworks.append(fw)

    return stacks, extensions, test_pattern, frameworks


async def _run_git(path: Path, *args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return (stdout or b"").decode(errors="replace").strip()
    except Exception:
        return ""

async def _git_remote(path: Path) -> str:
    url = await _run_git(path, "remote", "get-url", "origin")
    # Convert SSH to HTTPS for display
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):].rstrip(".git")
    return url

async def _git_branch(path: Path) -> str:
    return await _run_git(path, "rev-parse", "--abbrev-ref", "HEAD")
