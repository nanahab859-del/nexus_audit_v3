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

def detect_languages(target_path: Path, max_depth: int = 5) -> Set[str]:
    """Detect programming languages in target directory by scanning file extensions."""
    languages: Set[str] = set()
    if not target_path.exists(): return languages
    try:
        for file_path in target_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(target_path)
                if len(relative_path.parts) > max_depth: continue
                if any(part.startswith(".") or part in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build") 
                       for part in relative_path.parts): continue
                ext = file_path.suffix.lower()
                if ext in LANGUAGE_EXTENSIONS:
                    languages.add(LANGUAGE_EXTENSIONS[ext])
    except (PermissionError, OSError): pass
    return languages

def is_language_supported(scanner_languages: list[str], detected_languages: Set[str]) -> bool:
    """Check if any scanner language is supported by detected languages."""
    if not detected_languages: return True
    scanner_set = set(lang.lower() for lang in scanner_languages)
    return bool(scanner_set & detected_languages)
