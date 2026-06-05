"""File discovery — walk project tree, classify files by language, respect .gitignore."""

from typing import cast, Optional, Any
from dataclasses import dataclass
from pathlib import Path

try:
    import pathspec
except ImportError:
    pathspec = None


LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
}

# Directories to always skip
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "env",
    ".tox",
    "dist",
    "build",
    "*.egg-info",
}

# File extensions to skip
SKIP_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".so",
    ".o",
    ".a",
    ".dll",
    ".exe",
    ".class",
    ".jar",
    ".zip",
    ".tar",
    ".gz",
    ".lock",
}


@dataclass
class DiscoveredFile:
    """Represents a discovered file with metadata."""

    path: Path  # absolute path
    relative: str  # relative to project root (used in Finding.file)
    language: str  # "python", "javascript", "unknown", etc.
    size_bytes: int


def _is_binary(content: bytes, max_bytes: int = 8192) -> bool:
    """Check if first max_bytes of content looks like binary data."""
    # Check for null bytes, which are common in binary files
    return b"\x00" in content[:max_bytes]


def _classify_language(path: Path) -> str:
    """
    Classify file language by extension, with shebang override.
    Returns language name or "unknown".
    """
    # Check shebang line first (override extension classification)
    try:
        with open(path, "rb") as f:
            first_bytes = f.read(200)
            if first_bytes.startswith(b"#!"):
                line = first_bytes.split(b"\n")[0].decode("utf-8", errors="ignore")
                if "python" in line:
                    return "python"
                elif "ruby" in line:
                    return "ruby"
                elif "node" in line or "javascript" in line:
                    return "javascript"
                elif "bash" in line or "sh" in line:
                    return "shell"
    except (OSError, UnicodeDecodeError):
        pass

    # Fall back to extension classification
    suffix = path.suffix.lower()
    return LANGUAGE_MAP.get(suffix, "unknown")


def _load_gitignore_spec(project_root: Path) -> Optional[Any]:
    """Load .gitignore as a PathSpec for matching, or None if missing/pathspec unavailable."""
    if pathspec is None:
        return None

    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return None

    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            patterns = f.read().splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except Exception:
        # Ignore malformed .gitignore
        return None


def discover(
    project_root: Path,
    respect_gitignore: bool = True,
) -> list[DiscoveredFile]:
    """
    Walk project_root recursively and discover files.

    Skips: .git/, __pycache__/, node_modules/, *.pyc, binary files.
    Classifies files by extension + shebang line.
    Respects .gitignore if present and respect_gitignore=True.
    Returns sorted list (by relative path) for deterministic output.

    Args:
        project_root: root directory to walk
        respect_gitignore: if True and .gitignore exists, exclude matched files

    Returns:
        list[DiscoveredFile] sorted by relative path
    """
    project_root = project_root.resolve()
    discovered: list[DiscoveredFile] = []

    spec = _load_gitignore_spec(project_root) if respect_gitignore else None

    for item in project_root.rglob("*"):
        # Get relative path for comparison
        try:
            rel_path = item.relative_to(project_root)
        except ValueError:
            # Should not happen, but skip if it does
            continue

        rel_str = str(rel_path).replace("\\", "/")

        # Skip directories in SKIP_DIRS
        if item.is_dir():
            if item.name in SKIP_DIRS:
                continue
            continue  # We only want files, not directories

        # Skip files in .git, __pycache__, etc.
        parts = rel_path.parts
        if any(part in SKIP_DIRS for part in parts):
            continue

        # Skip by extension
        if item.suffix.lower() in SKIP_EXTENSIONS:
            continue

        # Respect .gitignore
        if spec and spec.match_file(rel_str):
            continue

        # Skip binary files
        try:
            with open(item, "rb") as f:
                header = f.read(8192)
                if _is_binary(header):
                    continue
        except (OSError, PermissionError):
            continue

        # Classify and add
        language = _classify_language(item)
        try:
            size_bytes = item.stat().st_size
        except OSError:
            continue

        discovered.append(
            DiscoveredFile(
                path=item,
                relative=rel_str,
                language=language,
                size_bytes=size_bytes,
            )
        )

    # Sort by relative path for deterministic output
    discovered.sort(key=lambda f: f.relative)
    return discovered
