from pathlib import Path
from typing import Set, Optional

__all__ = ["LANGUAGE_EXTENSIONS", "detect", "detect_languages", "is_language_supported"]

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".html": "html", ".htm": "html", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".java": "java", ".c": "c", ".cpp": "cpp",
    ".h": "c", ".hpp": "cpp", ".css": "css", ".scss": "scss",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".md": "markdown", ".toml": "toml", ".sh": "shell",
    ".bash": "shell", ".jinja": "jinja", ".j2": "jinja",
}

EXACT_MATCH_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile":   "makefile",
    "Jenkinsfile": "groovy",
}

EXTENSION_MAP: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".html": "html", ".htm": "html", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".java": "java", ".c": "c", ".cpp": "cpp",
    ".h": "c", ".hpp": "cpp", ".css": "css", ".scss": "scss",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".md": "markdown", ".toml": "toml", ".sh": "shell",
    ".bash": "shell", ".jinja": "jinja", ".j2": "jinja",
}

def detect(file_path: str | Path) -> str:
    """
    Return the programming language for a given file.
    Checks exact filename first, then extension (case‑insensitive).
    Returns "unknown" if nothing matches.
    """
    path = Path(file_path)
    filename = path.name
    
    # 1. Exact filename match
    if filename in EXACT_MATCH_MAP:
        return EXACT_MATCH_MAP[filename]
        
    # 2. Extension match
    ext = path.suffix.lower()
    return EXTENSION_MAP.get(ext, "unknown")
