import asyncio
import logging
import uuid
import re
import os
import ast as ast_module
import re as re_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from core.primitives.models import ModuleEntry, ProjectDNA, to_dict
from core.primitives.events import EventBus, EventType
from core.infra.file_discovery import discover
from core.infra.language_detection import detect

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


def _derive_root_packages(
    project_root: Path,
    files: list,
    app_mappings: Optional[List[Dict]],
) -> List[str]:
    """
    Determine the root package names to pass to grimp.build_graph().

    If app_mappings is provided, use the top-level directory component of each
    path_prefix as a root package.  Otherwise fall back to the top-level
    directory of every discovered file.
    """
    roots: Set[str] = set()
    if app_mappings:
        for mapping in app_mappings:
            prefix = mapping.get("path_prefix", "")
            if prefix:
                roots.add(prefix.replace("\\", "/").split("/")[0])
    if not roots:
        for f in files:
            parts = f.relative_path.replace("\\", "/").split("/")
            if parts[0] not in ("src", "backend", "lib", "source"):
                roots.add(parts[0])
            elif len(parts) > 1:
                roots.add(parts[1])
    # Strip any .py suffix that may have crept in, keep only valid identifiers
    valid_roots = []
    for r in roots:
        clean = r.removesuffix(".py")
        if clean and clean != "." and clean.isidentifier():
            # grimp requires top-level packages (directories with __init__.py), not single files
            if (project_root / clean / "__init__.py").exists():
                valid_roots.append(clean)
    return valid_roots


def _imports_from_grimp(graph: Any, module_path: str) -> dict[str, int]:
    """
    Extract direct imports for *module_path* from a grimp graph.
    Returns {imported_module_path: line_number}, matching the ModuleEntry.imports contract.
    """
    imports: dict[str, int] = {}
    try:
        for target in graph.find_modules_directly_imported_by(module_path):
            details = graph.get_import_details(importer=module_path, imported=target)
            if details:
                imports[target] = details[0]["line_number"]
            else:
                imports[target] = 1  # line unknown — use conventional placeholder
    except Exception as exc:  # pragma: no cover
        logger.debug("grimp: could not read imports for %s: %s", module_path, exc)
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

    # ------------------------------------------------------------------
    # Build grimp import graph (once, for all Python files in the project)
    # exclude_type_checking_imports=True ensures TYPE_CHECKING-guarded
    # imports are never counted as real runtime dependencies (Problem B).
    # ------------------------------------------------------------------
    grimp_graph: Any = None
    try:
        import sys
        import grimp  # type: ignore[import-untyped]
        root_packages = _derive_root_packages(project_root, files, app_mappings)
        if root_packages:
            original_sys_path = list(sys.path)
            try:
                sys.path.insert(0, str(project_root))
                grimp_graph = await asyncio.to_thread(
                    grimp.build_graph,
                    *root_packages,
                    exclude_type_checking_imports=True,
                )
                logger.info("grimp graph built for packages: %s", root_packages)
            finally:
                sys.path = original_sys_path
    except Exception as exc:
        logger.exception(
            "grimp: graph build failed, falling back to AST parser"
        )
        grimp_graph = None

    await bus.publish_progress("dna_builder", 50, "Parsing files...")

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

        # Exclude Django migration auto-generated files — they produce noise
        # and are not architectural decisions worth tracking.
        if ".migrations." in f".{module_path}.":
            continue

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
                pass
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
            parse_status="ok",
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
