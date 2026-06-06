from pathlib import Path
from typing import Set

# File extension to language mapping
LANGUAGE_EXTENSIONS = {
    "py": "python",
    "pyc": "python",
    "pyx": "python",
    "pyi": "python",
    
    "java": "java",
    "class": "java",
    "jar": "java",
    
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    
    "go": "go",
    
    "cpp": "c++",
    "cc": "c++",
    "cxx": "c++",
    "c++": "c++",
    "h": "c++",
    "hpp": "c++",
    
    "c": "c",
    
    "rs": "rust",
    
    "rb": "ruby",
    
    "php": "php",
    
    "cs": "csharp",
    
    "swift": "swift",
    
    "kt": "kotlin",
    
    "scala": "scala",
    
    "groovy": "groovy",
    
    "clj": "clojure",
    "cljs": "clojure",
    "edn": "clojure",
}

def detect_languages(target_path: Path, max_depth: int = 5) -> Set[str]:
    """
    Detect programming languages in target directory by scanning file extensions.
    
    Args:
        target_path: Root directory to scan
        max_depth: Maximum directory depth to search
    
    Returns:
        Set of detected language names (e.g., {"python", "javascript"})
    """
    languages: Set[str] = set()
    
    if not target_path.exists():
        return languages
    
    try:
        # Walk directory tree
        for file_path in target_path.rglob("*"):
            if file_path.is_file():
                # Check depth
                relative_path = file_path.relative_to(target_path)
                if len(relative_path.parts) > max_depth:
                    continue
                
                # Skip hidden and build directories
                if any(part.startswith(".") or part in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build") 
                       for part in relative_path.parts):
                    continue
                
                # Get file extension
                ext = file_path.suffix.lstrip(".").lower()
                if ext in LANGUAGE_EXTENSIONS:
                    languages.add(LANGUAGE_EXTENSIONS[ext])
    
    except (PermissionError, OSError):
        pass
    
    return languages


def is_language_supported(scanner_languages: list[str], detected_languages: Set[str]) -> bool:
    """
    Check if any scanner language is supported by detected languages.
    
    Args:
        scanner_languages: Languages the scanner supports (from BaseScanner.languages)
        detected_languages: Languages detected in the target directory
    
    Returns:
        True if there's any overlap, False if no compatible languages found
    """
    if not detected_languages:
        # If we couldn't detect any languages, allow the scanner to run anyway
        # (it might handle unknown types gracefully)
        return True
    
    scanner_set = set(lang.lower() for lang in scanner_languages)
    return bool(scanner_set & detected_languages)
