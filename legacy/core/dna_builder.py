import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import tree_sitter

from core.file_discovery import discover
from core.events import EventBus, bus

# Load languages conditionally
LANGUAGES = {}

try:
    import tree_sitter_python
    LANGUAGES["python"] = tree_sitter.Language(tree_sitter_python.language())
except ImportError:
    pass

try:
    import tree_sitter_javascript
    LANGUAGES["javascript"] = tree_sitter.Language(tree_sitter_javascript.language())
except ImportError:
    pass

try:
    import tree_sitter_go
    LANGUAGES["go"] = tree_sitter.Language(tree_sitter_go.language())
except ImportError:
    pass


@dataclass
class ModuleEntry:
    module_path: str       # "nexus_core.models.user" (or similar for other langs)
    file_path: str         # absolute path
    relative_path: str     # relative to project root
    app: str               # first path segment
    imports: list[str]
    defined_names: list[str]
    is_test: bool
    lines_of_code: int
    language: str          # added for multi-language support

@dataclass
class ProjectDNA:
    modules: dict[str, ModuleEntry]
    apps: list[str]
    physical_files: list[str]
    built_at: datetime
    project_root: Path


def get_queries(lang: str) -> tuple[str, str]:
    if lang == "python":
        import_query = """
        (import_statement name: (dotted_name) @import_name)
        (import_from_statement module_name: (dotted_name) @import_from name: (dotted_name) @import_name)
        """
        def_query = """
        (class_definition name: (identifier) @def_name)
        (function_definition name: (identifier) @def_name)
        (assignment left: (identifier) @def_name)
        """
        return import_query, def_query
    elif lang == "javascript":
        import_query = """
        (import_statement source: (string) @import_source)
        (call_expression function: (identifier) @req_fn arguments: (arguments (string) @import_source) (#eq? @req_fn "require"))
        """
        def_query = """
        (class_declaration name: (identifier) @def_name)
        (function_declaration name: (identifier) @def_name)
        (variable_declarator name: (identifier) @def_name)
        """
        return import_query, def_query
    elif lang == "go":
        import_query = """
        (import_spec path: (interpreted_string_literal) @import_path)
        """
        def_query = """
        (type_spec name: (type_identifier) @def_name)
        (function_declaration name: (identifier) @def_name)
        (method_declaration name: (field_identifier) @def_name)
        """
        return import_query, def_query
    return "", ""


async def build_dna(project_root: Path, event_bus: EventBus = bus) -> ProjectDNA:
    """
    Builds the Live Module Registry (DNA) using Tree-Sitter.
    Supports Python, JavaScript, and Go out-of-the-box if grammars are installed.
    """
    project_root = project_root.resolve()
    discovered_files = discover(project_root)
    
    modules: dict[str, ModuleEntry] = {}
    apps_set: set[str] = set()
    physical_files: list[str] = []
    
    for file_info in discovered_files:
        lang_name = file_info.language
        if lang_name not in LANGUAGES:
            continue
            
        rel_str = file_info.relative
        physical_files.append(rel_str)
        
        path_without_ext = os.path.splitext(rel_str)[0]
        
        parts = path_without_ext.split("/")
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
            
        module_path = ".".join(parts)
        if not module_path:
            continue
            
        app = parts[0]
        apps_set.add(app)
        
        file_path = project_root / rel_str
        
        imports: list[str] = []
        defined_names: list[str] = []
        lines_of_code = 0
        
        try:
            source_bytes = file_path.read_bytes()
            source_code = source_bytes.decode("utf-8")
            
            for line in source_code.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith(("//", "#")):
                    lines_of_code += 1
                    
            ts_lang = LANGUAGES[lang_name]
            parser = tree_sitter.Parser(ts_lang)
            tree = parser.parse(source_bytes)
            
            import_q_str, def_q_str = get_queries(lang_name)
            
            if import_q_str:
                query = ts_lang.query(import_q_str)
                captures = query.captures(tree.root_node)  # type: ignore
                for node, capture_name in captures:
                    val = source_bytes[node.start_byte:node.end_byte].decode("utf-8").strip("\"'")
                    if val and val not in imports:
                        imports.append(val)
                        
            if def_q_str:
                query = ts_lang.query(def_q_str)
                captures = query.captures(tree.root_node)  # type: ignore
                for node, capture_name in captures:
                    val = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                    if val and val not in defined_names:
                        defined_names.append(val)
                        
        except Exception as e:
            await event_bus.publish_log("warning", f"Error parsing {rel_str}: {e}")
            
        is_test = "test_" in file_path.name or "_test." in file_path.name or "/tests/" in rel_str or "/test/" in rel_str
        
        modules[module_path] = ModuleEntry(
            module_path=module_path,
            file_path=str(file_path),
            relative_path=rel_str,
            app=app,
            imports=sorted(imports),
            defined_names=sorted(defined_names),
            is_test=is_test,
            lines_of_code=lines_of_code,
            language=lang_name
        )
        
    return ProjectDNA(
        modules=modules,
        apps=sorted(list(apps_set)),
        physical_files=physical_files,
        built_at=datetime.now(timezone.utc),
        project_root=project_root
    )
