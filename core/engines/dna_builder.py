import asyncio
import logging
import uuid
import re
import os
import ast as ast_module
import re as re_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.primitives.models import ModuleEntry, ProjectDNA, to_dict
from core.primitives.events import EventBus, EventType
from core.infra.file_discovery import discover
from core.infra.language_detection import detect

def _derive_root_packages(files: list) -> list[str]:
    roots = set()
    for f in files:
        if f.language == "python":
            parts = f.relative_path.replace("\\", "/").split("/")
            root = parts[0]
            if root.endswith(".py"):
                root = root[:-3]
            if root:
                roots.add(root)
    return list(roots)

def _imports_from_grimp(graph, module_path: str) -> dict[str, int]:
    imports = {}
    for target in graph.find_modules_directly_imported_by(module_path):
        details = graph.get_import_details(importer=module_path, imported=target)
        if details:
            imports[target] = details[0]["line_number"]
    return imports

logger = logging.getLogger(__name__)

def _parse_python_imports(source: str, module_path: str) -> dict[str, int]:
    """
    Parse Python imports from source code using the built-in ast module.
    Returns {imported_module_path: line_number}.
    
    Converts dotted import paths to the same format used in module_path keys:
    e.g. "from core.infra.utils import deep_merge" -> {"core.infra.utils": 10}
    """
    imports: dict[str, int] = {}
    try:
        tree = ast_module.parse(source)
    except SyntaxError:
        return imports

    for node in ast_module.walk(tree):
        if isinstance(node, ast_module.Import):
            for alias in node.names:
                imports[alias.name] = node.lineno

        elif isinstance(node, ast_module.ImportFrom):
            if node.level > 0 and not node.module:
                # Pure relative: "from . import foo" or "from .. import bar"
                parts = module_path.split(".")
                base  = ".".join(parts[:len(parts) - node.level])
                for alias in node.names:
                    resolved = f"{base}.{alias.name}" if base else alias.name
                    imports[resolved] = node.lineno
            elif node.module:
                # Resolve relative imports: level > 0 means relative
                if node.level > 0:
                    # Relative import — prefix with current package
                    parts = module_path.split(".")
                    base = ".".join(parts[:-(node.level)])
                    resolved = f"{base}.{node.module}" if base else node.module
                else:
                    resolved = node.module
                imports[resolved] = node.lineno

    return imports


_JS_IMPORT_RE = re_module.compile(
    r"""(?:import\s+(?:.*?\s+from\s+)?|require\s*\(\s*)['"]([^'"]+)['"]""",
    re_module.MULTILINE,
)

def _parse_js_imports(source: str, file_path: Path) -> dict[str, int]:
    """
    Parse ES6 import and CommonJS require statements.
    Returns {module_specifier: line_number}.
    Only captures relative imports (starting with ./ or ../).
    External packages are not tracked — they are framework/external.
    """
    imports: dict[str, int] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        for match in _JS_IMPORT_RE.finditer(line):
            specifier = match.group(1)
            if specifier.startswith("."):   # relative only
                imports[specifier] = i
    return imports


_COMMENT_PREFIXES: dict[str, list[str]] = {
    "python":     ["#"],
    "ruby":       ["#"],
    "shell":      ["#"],
    "yaml":       ["#"],
    "toml":       ["#"],
    "javascript": ["//"],
    "typescript": ["//"],
    "java":       ["//"],
    "go":         ["//"],
    "rust":       ["//"],
    "kotlin":     ["//"],
    "swift":      ["//"],
    "cpp":        ["//"],
    "c":          ["//"],
    "csharp":     ["//"],
    "php":        ["//", "#"],
}

def _count_loc(lines: list[str], language: str) -> int:
    """Count non-blank, non-single-line-comment lines."""
    prefixes = tuple(_COMMENT_PREFIXES.get(language, []))
    count = 0
    in_block = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Block comment toggle (/* ... */) for C-family languages
        if language in ("javascript","typescript","java","go","rust","cpp","c","csharp","kotlin","swift","php"):
            if "/*" in stripped:
                in_block = True
            if "*/" in stripped:
                in_block = False
                continue
            if in_block:
                continue
        if prefixes and stripped.startswith(prefixes):
            continue
        count += 1
    return count


async def build_dna(
    project_root: Path,
    bus: EventBus,
    app_mappings: Optional[List[Dict]] = None
) -> ProjectDNA:
    
    await bus.publish_log("info", f"Starting DNA construction for {project_root}")
    await bus.publish_progress("dna_builder", 0, "Discovering files...")
    
    files = await discover(project_root)
    total_files = len(files)
    modules: Dict[str, ModuleEntry] = {}
        
    await bus.publish_progress("dna_builder", 50, "Parsing files...")

    root_packages = _derive_root_packages(files)
    grimp_graph = None
    if root_packages:
        import sys
        inserted = False
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
            inserted = True
        try:
            import grimp
            grimp_graph = grimp.build_graph(
                *root_packages,
                exclude_type_checking_imports=True,
            )
        except Exception as e:
            logger.warning("grimp: graph build failed or partial: %s", e)
            grimp_graph = None
        finally:
            if inserted and str(project_root) in sys.path:
                sys.path.remove(str(project_root))
    
    for f in files:
        lang = f.language           # already detected by discover()
        if lang == "unknown":
            continue
        file_path = f.absolute_path

        rel_path = Path(f.relative_path)
        if file_path.name == "__init__.py":
            module_path = str(rel_path.parent).replace(os.sep, ".").strip(".")
        else:
            module_path = str(rel_path.with_suffix("")).replace(os.sep, ".").strip(".")

        if ".migrations." in f".{module_path}.":
            continue

        # App assignment
        app = "unknown"
        if app_mappings:
            for mapping in app_mappings:
                if f.relative_path.startswith(mapping.get("path_prefix", "")):
                    app = mapping.get("app", "unknown")
                    break
        if app == "unknown":
            parts = f.relative_path.replace("\\", "/").split("/")
            if parts[0] in ("src", "backend", "lib", "source") and len(parts) > 1:
                app = parts[1]
            else:
                app = parts[0]

        # Read source
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Cannot read %s: %s", file_path, e)
            continue

        parse_status = "ok"

        # Parse imports
        if lang == "python":
            if grimp_graph is not None and module_path in grimp_graph.modules:
                imports = _imports_from_grimp(grimp_graph, module_path)
            else:
                imports = _parse_python_imports(source, module_path)
        elif lang in ("javascript", "typescript"):
            imports = _parse_js_imports(source, file_path)
        else:
            imports = {}   # future: tree-sitter for other languages

        # Parse defined names and wildcard imports (Python only)
        defined_names: list[str] = []
        has_wildcard = False
        if lang == "python":
            try:
                tree = ast_module.parse(source)
                defined_names = [
                    node.name
                    for node in ast_module.walk(tree)
                    if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef, ast_module.ClassDef))
                ]
                # AST-based wildcard check — exact, no false positives from comments/strings
                has_wildcard = any(
                    isinstance(node, ast_module.ImportFrom)
                    and any(alias.name == "*" for alias in node.names)
                    for node in ast_module.walk(tree)
                )
            except SyntaxError:
                parse_status = "error"
                logger.warning("AST syntax error in %s", module_path)
        elif lang in ("javascript", "typescript"):
            # JS/TS: check for export * from '...'
            has_wildcard = bool(re_module.search(r'\bexport\s+\*\s+from\b', source))

        # LOC
        lines = source.splitlines()
        loc = _count_loc(lines, lang)

        modules[module_path] = ModuleEntry(
            module_path=module_path,
            file_path=file_path,
            relative_path=f.relative_path,
            app=app,
            imports=imports,
            defined_names=defined_names,
            is_test="test" in rel_path.parts or file_path.name.startswith("test_"),
            lines_of_code=loc,
            language=lang,
            parse_status=parse_status,
            has_wildcard_imports=has_wildcard,
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
