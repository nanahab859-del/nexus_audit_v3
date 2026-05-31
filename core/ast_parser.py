"""
AST-based import parser and classifier.

Parses all Python files in a project and extracts import statements,
classifying each import as first-party, third-party, stdlib, or django.
"""

import ast
import sys
from pathlib import Path
from typing import Set

from core.file_discovery import DiscoveredFile
from core.models import ImportInfo


def get_first_party_apps(project_root: Path, discovered_files: list[DiscoveredFile]) -> Set[str]:
    """
    Detect first-party app names by scanning project structure.

    Strategy:
    1. Scan top-level directories in project_root for Django app markers
       (presence of models.py or views.py)
    2. Extract directory name as app name
    3. Return set of first-party app names

    Returns:
        Set of first-party app names (e.g., {"core", "users", "products"})
    """
    first_party = set()

    # Heuristic 1: Top-level directories with Django markers (models.py, views.py)
    try:
        for item in project_root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                # Check for Django markers
                if (item / "models.py").exists() or (item / "views.py").exists():
                    first_party.add(item.name)
    except (OSError, PermissionError):
        pass

    # Heuristic 2: Discover from file paths — extract top-level module names
    for file in discovered_files:
        if file.language == "python":
            # Convert relative path to module path (e.g., "core/models.py" → "core")
            try:
                rel_path = file.relative
                parts = rel_path.split("/")
                if len(parts) > 1 and not rel_path.startswith("."):
                    top_module = parts[0]
                    if top_module and not top_module.startswith("_"):
                        first_party.add(top_module)
            except (ValueError, AttributeError):
                pass

    return first_party


def classify_import(module_name: str, first_party_apps: Set[str]) -> str:
    """
    Classify an imported module as first_party, django, stdlib, or third_party.

    Strategy:
    1. Check if it's a first-party app (top-level module in first_party_apps)
    2. Check if it's django.* (framework)
    3. Check if it's in sys.stdlib_module_names (Python 3.10+)
    4. Default to third_party

    Args:
        module_name: Full dotted module name (e.g., "django.db.models", "requests")
        first_party_apps: Set of known first-party app names

    Returns:
        Classification: "first_party", "django", "stdlib", or "third_party"
    """
    if not module_name:
        return "third_party"

    # Extract top-level module name
    top_level = module_name.split(".")[0]

    # Check first-party
    if top_level in first_party_apps:
        return "first_party"

    # Check django
    if top_level == "django" or module_name.startswith("django."):
        return "django"

    # Check stdlib (Python 3.10+)
    if hasattr(sys, "stdlib_module_names"):
        if top_level in sys.stdlib_module_names:
            return "stdlib"

    # Fallback for older Python versions — minimal stdlib list
    common_stdlib = {
        "os", "sys", "re", "json", "math", "time", "datetime", "collections",
        "itertools", "functools", "pathlib", "typing", "asyncio", "logging",
        "unittest", "subprocess", "threading", "multiprocessing", "socket",
        "urllib", "http", "ssl", "hashlib", "hmac", "secrets", "base64",
        "pickle", "csv", "shutil", "tempfile", "glob", "fnmatch", "linecache",
        "importlib", "ast", "inspect", "types", "copy", "enum", "dataclasses",
    }
    if top_level in common_stdlib:
        return "stdlib"

    return "third_party"


def parse_project_imports(
    project_root: Path,
    discovered_files: list[DiscoveredFile],
) -> list[ImportInfo]:
    """
    Parse all Python files in the project and extract import statements.

    Uses the `ast` module to safely walk each file's AST and extract both
    `import` and `from ... import` statements. Skips files with syntax errors
    (logging a warning) and handles edge cases like circular imports gracefully.

    Args:
        project_root: Root directory of the project
        discovered_files: List of DiscoveredFile objects from file_discovery

    Returns:
        List of ImportInfo objects representing all imports found
    """
    first_party_apps = get_first_party_apps(project_root, discovered_files)
    imports: list[ImportInfo] = []

    # Filter to only Python files
    python_files = [f for f in discovered_files if f.language == "python"]

    for file_info in python_files:
        file_path = project_root / file_info.relative

        if not file_path.exists():
            continue

        try:
            source_code = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError:
            # Log but continue — don't crash on syntax errors
            continue

        # Walk the AST and find all imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # import X, Y, Z
                for alias in node.names:
                    module_name = alias.name or ""
                    if module_name:
                        classification = classify_import(module_name, first_party_apps)
                        imports.append(
                            ImportInfo(
                                importer=file_info.relative,
                                imported=module_name,
                                line=getattr(node, "lineno", 0),
                                import_type="import",
                                classification=classification,
                            )
                        )

            elif isinstance(node, ast.ImportFrom):
                # from X import Y, Z
                module_name = node.module or ""
                if module_name:
                    classification = classify_import(module_name, first_party_apps)
                    for alias in node.names:
                        name = alias.name or ""
                        if name and name != "*":
                            imports.append(
                                ImportInfo(
                                    importer=file_info.relative,
                                    imported=f"{module_name}.{name}",
                                    line=getattr(node, "lineno", 0),
                                    import_type="from_import",
                                    classification=classification,
                                )
                            )
                        elif name == "*":
                            # Wildcard import: record the module itself
                            imports.append(
                                ImportInfo(
                                    importer=file_info.relative,
                                    imported=module_name,
                                    line=getattr(node, "lineno", 0),
                                    import_type="from_import_star",
                                    classification=classification,
                                )
                            )

    return imports
