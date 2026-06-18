import asyncio
import os
import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from core.infra.language_detection import detect

try:
    import pathspec
except ImportError:
    pathspec = None

logger = logging.getLogger(__name__)

@dataclass
class DiscoveredFile:
    absolute_path: Path
    relative_path: str
    language: str
    size_bytes: int

def _walk_project(
    project_root: Path, 
    respect_gitignore: bool, 
    exclude_patterns: List[str]
) -> List[DiscoveredFile]:
    
    discovered: List[DiscoveredFile] = []
    EXCLUDE_DIRS = {
        ".git", ".venv", "venv", "__pycache__", ".tox", 
        ".mypy_cache", ".pytest_cache", ".idea", ".vscode", 
        ".DS_Store", "dist", "build", "coverage"
    }
    
    visited = set()
    spec = None
    if respect_gitignore:
        gitignore = project_root / ".gitignore"
        if gitignore.exists() and pathspec:
            spec = pathspec.PathSpec.from_lines('gitwildmatch', gitignore.read_text().splitlines())
            
    for root, dirs, files in os.walk(project_root):
        root_path = Path(root)
        
        # Symlink protection
        resolved_root = root_path.resolve()
        if resolved_root in visited:
            continue
        visited.add(resolved_root)
        
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            file_path = root_path / file
            rel_path = file_path.relative_to(project_root)
            
            # Gitignore check
            if spec and spec.match_file(str(rel_path)):
                continue
                
            # Exclude patterns check
            if exclude_patterns:
                rel_str = str(rel_path).replace("\\", "/")
                if any(fnmatch.fnmatch(rel_str, p) for p in exclude_patterns):
                    continue
                if any(fnmatch.fnmatch(file, p) for p in exclude_patterns):
                    continue
                
            # Size check
            try:
                stat = file_path.stat()
            except OSError:
                continue
            
            if stat.st_size > 1_000_000 or ".min." in file:
                continue
                
            # Binary check
            try:
                with open(file_path, "rb") as f:
                    if b'\0' in f.read(8192):
                        continue
            except OSError:
                continue
                
            # Detect language
            lang = detect(file_path)
            
            discovered.append(DiscoveredFile(
                absolute_path=file_path.absolute(),
                relative_path=str(rel_path),
                language=lang,
                size_bytes=stat.st_size
            ))
            
    return sorted(discovered, key=lambda x: x.relative_path)

async def discover(
    project_root: Path,
    respect_gitignore: bool = True,
    exclude_patterns: Optional[List[str]] = None
) -> List[DiscoveredFile]:
    """
    Walk project_root and return all source files.
    """
    return await asyncio.to_thread(
        _walk_project, project_root, respect_gitignore, exclude_patterns or []
    )
