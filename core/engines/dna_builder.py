import asyncio
import logging
import uuid
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.primitives.models import ModuleEntry, ProjectDNA, to_dict
from core.primitives.events import EventBus, EventType
from core.infra.file_discovery import discover
from core.infra.language_detection import detect

# Assuming tree_sitter is installed and available
try:
    from tree_sitter import Language, Parser
except ImportError:
    Language = None
    Parser = None

logger = logging.getLogger(__name__)

async def build_dna(
    project_root: Path,
    bus: EventBus,
    app_mappings: Optional[List[Dict]] = None
) -> ProjectDNA:
    
    await bus.publish_log("info", f"Starting DNA construction for {project_root}")
    await bus.publish_progress("dna_builder", 0, "Discovering files...")
    
    files = list(discover(project_root))
    total_files = len(files)
    modules: Dict[str, ModuleEntry] = {}
    
    # 2. Filter files
    filtered_files = []
    for f in files:
        file_path = Path(f.absolute)
        if file_path.stat().st_size > 1024 * 1024:
            continue
        if ".min." in file_path.name or file_path.suffix in [".min.js", ".min.css"]:
            continue
        filtered_files.append((f, file_path)) # Store as tuple (FileInfo, Path)
        
    await bus.publish_progress("dna_builder", 50, "Parsing files...")
    
    # 3. Process files
    for i, (f, file_path) in enumerate(filtered_files):
        lang = detect(file_path)
        if not lang:
            logger.warning(f"Unsupported language for file: {file_path}")
            continue
            
        # Determine module_path
        rel_path = Path(f.relative)
        if file_path.name == "__init__.py":
            module_path = str(rel_path.parent).replace(os.sep, ".")
        else:
            module_path = str(rel_path.with_suffix("")).replace(os.sep, ".")
            
        # Assign app
        app = "unknown"
        if app_mappings:
            for mapping in app_mappings:
                if str(rel_path).startswith(mapping.get("path_prefix", "")):
                    app = mapping.get("app", app)
        if app == "unknown":
            parts = str(rel_path).split(os.sep)
            if parts[0] in ["src", "backend", "lib", "source"]:
                app = parts[1] if len(parts) > 1 else "unknown"
            else:
                app = parts[0]

        # Calculate lines_of_code: non-blank, non-comment (for python)
        lines = file_path.read_text().splitlines()
        loc = 0
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                loc += 1
        
        modules[module_path] = ModuleEntry(
            module_path=module_path,
            file_path=file_path.absolute(),
            relative_path=str(rel_path),
            app=app,
            imports=[], # Real implementation needed
            defined_names=[], # Real implementation needed
            is_test="test" in rel_path.parts or file_path.name.startswith("test_"),
            lines_of_code=loc,
            language=lang,
            parse_status="ok",
            has_wildcard_imports=False
        )
        
    await bus.publish_progress("dna_builder", 100, "DNA construction complete.")
    
    apps = list({m.app for m in modules.values()})
    physical_files = [m.relative_path for m in modules.values()]
    
    return ProjectDNA(
        modules=modules,
        apps=apps,
        physical_files=physical_files,
        built_at=datetime.now(timezone.utc),
        project_root=project_root
    )
