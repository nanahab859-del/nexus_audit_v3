"""
Architecture analysis engine.

Builds the dependency graph, detects circular dependencies (iterative DFS),
identifies ghost files, computes coupling matrix, and calculates health scores.
"""

from collections import defaultdict
from pathlib import Path
from typing import Set, Dict, Any

from core.models import ImportInfo, ArchitectureResult, GraphNode, GraphEdge, CouplingMatrix
from core.file_discovery import DiscoveredFile


# Bootstrap files exempt from cross-app violations
BOOTSTRAP_LEAVES = {
    "asgi", "wsgi", "settings", "celery", "manage", "routing", "apps", "admin",
}

# Keywords for signal/receiver modules
SIGNAL_LEAVES = {"signals", "receivers", "signal", "receiver"}

# Keywords for task/async modules
TASK_KEYWORDS = {"task", "tasks", "celery", "worker", "beat"}


def _get_app_name(module_path: str) -> str:
    """
    Extract top-level app name from a module path or file path.

    Handles both:
    - Dotted module names (e.g., 'core.models' → 'core')
    - File paths (e.g., 'core/models.py' → 'core')
    """
    # If it looks like a file path (contains / or \), extract directory name
    if "/" in module_path or "\\" in module_path:
        return module_path.split("/")[0].split("\\")[0]
    # Otherwise treat as dotted module name
    return module_path.split(".")[0]


def _get_file_leaf(rel_path: str) -> str:
    """Extract filename without extension (e.g., 'models' from 'core/models.py')."""
    path_obj = Path(rel_path)
    return path_obj.stem.lower()


def classify_connection(source: str, target: str, first_party_apps: Set[str]) -> tuple[str, int, bool]:
    """
    Classify a cross-app import connection.

    Returns: (connection_type, severity_penalty, is_violation)

    Classification order (see old tool's classify_connection):
    1. Same app → "internal", 0, False
    2. Framework/stdlib target → "framework", 0, False
    3. Source not first-party → "external", 0, False
    4. Bootstrap files → "django_bootstrap", 0, False (EXEMPT)
    5. Signal/receiver modules → "django_signal", 0, False (allowed)
    6. Celery/task modules → "celery_task", 0, False (allowed)
    7. Test files → "test_cross_app", 0, False (excluded from scoring)
    8. Everything else → "cross_app_import", 5, True (VIOLATION)
    """
    src_parts = source.split(".")
    tgt_parts = target.split(".")
    src_app = src_parts[0]
    tgt_app = tgt_parts[0]

    # 1. Same app
    if src_app == tgt_app:
        return "internal", 0, False

    # 2. Framework/stdlib target
    if tgt_app == "django" or target.startswith("django."):
        return "framework", 0, False
    if target in {"os", "sys", "re", "json", "pathlib", "typing", "asyncio"}:
        return "stdlib", 0, False

    # 3. Source not first-party
    if src_app not in first_party_apps:
        return "external", 0, False

    # From here on, both source and target are first-party
    if src_app in first_party_apps and tgt_app in first_party_apps:
        src_leaf = src_parts[-1].lower()
        tgt_leaf = tgt_parts[-1].lower()
        src_lower = source.lower()
        tgt_lower = target.lower()

        # 4. Django bootstrap files
        if src_leaf in BOOTSTRAP_LEAVES:
            return "django_bootstrap", 0, False

        # 5. Signal/receiver modules
        if (
            "django.dispatch" in tgt_lower
            or tgt_leaf in SIGNAL_LEAVES
            or src_leaf in SIGNAL_LEAVES
        ):
            return "django_signal", 0, False

        # 6. Celery/task modules
        if tgt_leaf in TASK_KEYWORDS or any(k in tgt_lower for k in TASK_KEYWORDS):
            return "celery_task", 0, False
        if any(k in src_lower for k in TASK_KEYWORDS):
            return "celery_task", 0, False

        # 7. Test files
        if "test" in src_lower:
            return "test_cross_app", 0, False

        # 8. Cross-app violation
        return "cross_app_import", 5, True

    return "unknown", 5, False


def find_circular_dependencies(
    imports: list[ImportInfo],
    first_party_apps: Set[str],
) -> list[list[str]]:
    """
    Detect circular dependencies using iterative stack-based DFS.

    This avoids Python's recursion limit by using an explicit stack instead
    of recursion. It also detects both cross-app and intra-app cycles.

    Args:
        imports: List of ImportInfo objects
        first_party_apps: Set of first-party app names

    Returns:
        List of cycles, each cycle is a list of module names forming the cycle
    """
    # Build adjacency graph (first-party only)
    graph: Dict[str, Set[str]] = defaultdict(set)

    for imp in imports:
        if imp.classification == "first_party" and imp.imported in first_party_apps:
            src_app = _get_app_name(imp.importer)
            tgt_app = _get_app_name(imp.imported)
            if src_app in first_party_apps and src_app != tgt_app:
                graph[src_app].add(tgt_app)

    # Iterative DFS to find cycles
    raw_cycles: list[list[str]] = []
    visited: Set[str] = set()

    for start in graph:
        if start in visited:
            continue

        # Stack entries: (node, neighbor_iterator)
        path: list[str] = []
        path_set: Set[str] = set()
        stack: list[tuple[str, Any]] = [(start, iter(graph.get(start, [])))]
        path.append(start)
        path_set.add(start)

        while stack:
            node, nbrs = stack[-1]
            try:
                nxt = next(nbrs)
                if nxt in path_set:
                    # Back-edge found → cycle
                    idx = path.index(nxt)
                    cycle = path[idx:] + [nxt]
                    if len(cycle) > 2:  # Ignore 2-node self-loops
                        raw_cycles.append(cycle)
                elif nxt not in visited:
                    path.append(nxt)
                    path_set.add(nxt)
                    stack.append((nxt, iter(graph.get(nxt, []))))
            except StopIteration:
                visited.add(node)
                stack.pop()
                if path and path[-1] == node:
                    path.pop()
                    path_set.discard(node)

    # Deduplicate by node-set
    seen: Set[frozenset] = set()
    unique_cycles: list[list[str]] = []

    for cycle in raw_cycles:
        key = frozenset(cycle)
        if key not in seen:
            seen.add(key)
            # Remove the repeated closing node
            nodes = cycle[:-1]
            unique_cycles.append(nodes)

    return unique_cycles


def find_ghost_files(
    project_root: Path,
    discovered_files: list[DiscoveredFile],
    imports: list[ImportInfo],
    first_party_apps: Set[str],
) -> list[str]:
    """
    Identify ghost files: files that exist but have zero imports and are not imported.

    A ghost file indicates dead code or missing module documentation.

    Args:
        project_root: Root directory
        discovered_files: List of discovered files
        imports: List of all imports
        first_party_apps: Set of first-party app names

    Returns:
        List of relative paths to ghost files
    """
    ghost_files: list[str] = []

    # Collect all files that are involved in imports (as importers or imported modules)
    importing_files: Set[str] = set()  # Files that do imports
    imported_files: Set[str] = set()  # Files that are imported

    for imp in imports:
        # Add the importer file
        importing_files.add(imp.importer)

        # For imported, we need to resolve the module to file path
        # e.g., "core.models" -> "core/models.py"
        if imp.classification in {"first_party", "django"}:
            imported_app = _get_app_name(imp.imported)
            if imported_app in first_party_apps:
                # Get the actual imported module name and convert to file path
                # For "core.models", we'd expect "core/models.py" to exist
                module_parts = imp.imported.split(".")
                potential_file = "/".join(module_parts) + ".py"
                imported_files.add(potential_file)

    # Check each discovered Python file
    for file_info in discovered_files:
        if file_info.language != "python":
            continue

        rel_path = file_info.relative

        # Skip excluded files
        if any(
            part in rel_path.lower()
            for part in {"migration", "test", "__pycache__", ".venv", "node_modules"}
        ):
            continue
        if rel_path.endswith("manage.py") or rel_path.endswith("__main__.py"):
            continue

        # Skip if in first-party apps
        app_name = _get_app_name(rel_path)
        if app_name not in first_party_apps:
            continue

        # A ghost file is one that:
        # - doesn't import anything (not in importing_files)
        # - and is not imported by anything (not in imported_files)
        if rel_path not in importing_files and rel_path not in imported_files:
            ghost_files.append(rel_path)

    return ghost_files


def build_coupling_matrix(
    imports: list[ImportInfo],
    first_party_apps: list[str],
) -> CouplingMatrix:
    """
    Build cross-app import coupling matrix.

    Args:
        imports: List of all imports
        first_party_apps: Ordered list of first-party app names

    Returns:
        CouplingMatrix with counts and violations
    """
    app_index = {app: idx for idx, app in enumerate(first_party_apps)}
    size = len(first_party_apps)

    # Initialize matrix and violations
    matrix = [[0 for _ in range(size)] for _ in range(size)]
    violations: list[dict] = []

    for imp in imports:
        if imp.classification != "first_party":
            continue

        src_app = _get_app_name(imp.importer)
        tgt_app = _get_app_name(imp.imported)

        if src_app not in app_index or tgt_app not in app_index or src_app == tgt_app:
            continue

        i = app_index[src_app]
        j = app_index[tgt_app]
        matrix[i][j] += 1

        # Check if this is a violation
        conn_type, _, is_violation = classify_connection(src_app, tgt_app, set(first_party_apps))
        if is_violation and imp.line > 0:
            violations.append(
                {
                    "from": src_app,
                    "to": tgt_app,
                    "file": imp.importer,
                    "line": imp.line,
                    "connection_type": conn_type,
                }
            )

    return CouplingMatrix(
        apps=first_party_apps,
        matrix=matrix,
        violations=violations,
    )


def calculate_app_health_score(
    app_name: str,
    metrics: Dict[str, Any],
    first_party_apps: Set[str],
) -> float:
    """
    Calculate architecture health score for an app (0–100).

    Penalties:
    - Circular dependencies: -5 per cycle
    - Cross-app violations: -2 per violation
    - Ghost files in app: -3 per file

    Args:
        app_name: Name of the app
        metrics: Dict with keys: 'circular_deps', 'violations', 'ghost_files'
        first_party_apps: Set of all first-party apps for bonus calculation

    Returns:
        Health score between 0 and 100
    """
    base_score = 100.0

    # Penalty for circular dependencies
    circular_deps = metrics.get("circular_deps", 0)
    base_score -= circular_deps * 5

    # Penalty for violations
    violations = metrics.get("violations", 0)
    base_score -= violations * 2

    # Penalty for ghost files
    ghost_files = metrics.get("ghost_files", 0)
    base_score -= ghost_files * 3

    # Bonus for core/infrastructure apps (they legitimately have more connections)
    if app_name in {"core", "gateway", "shared", "common"}:
        base_score += 10

    return max(0, min(100, base_score))


def analyze_architecture(
    project_root: Path,
    discovered_files: list[DiscoveredFile],
    imports: list[ImportInfo],
) -> ArchitectureResult:
    """
    Perform complete architecture analysis.

    This is the main orchestration function that:
    1. Identifies first-party apps
    2. Detects circular dependencies
    3. Finds ghost files
    4. Builds the dependency graph and coupling matrix
    5. Calculates health scores

    Args:
        project_root: Root directory of the project
        discovered_files: List of discovered files
        imports: List of all imports from AST parser

    Returns:
        ArchitectureResult with all analysis data
    """
    # Get first-party apps from file structure (already done in ast_parser, but recompute here)
    first_party_apps = sorted({_get_app_name(f.relative) for f in discovered_files
                                 if f.language == "python" and not f.relative.startswith(".")})
    first_party_set = set(first_party_apps)

    # Detect circular dependencies
    cycles = find_circular_dependencies(imports, first_party_set)

    # Find ghost files
    ghosts = find_ghost_files(project_root, discovered_files, imports, first_party_set)

    # Build coupling matrix
    coupling = build_coupling_matrix(imports, first_party_apps)

    # Count violations per app for health scoring
    violations_per_app: Dict[str, int] = defaultdict(int)
    for imp in imports:
        if imp.classification == "first_party":
            src_app = _get_app_name(imp.importer)
            tgt_app = _get_app_name(imp.imported)
            if src_app != tgt_app:
                conn_type, penalty, is_violation = classify_connection(src_app, tgt_app, first_party_set)
                if is_violation:
                    violations_per_app[src_app] += 1

    # Count cycles per app
    cycles_per_app: Dict[str, int] = defaultdict(int)
    for cycle in cycles:
        for app in set(cycle):
            cycles_per_app[app] += 1

    # Count ghosts per app
    ghosts_per_app: Dict[str, int] = defaultdict(int)
    for ghost in ghosts:
        app = _get_app_name(ghost)
        ghosts_per_app[app] += 1

    # Build health scores
    health_scores: Dict[str, float] = {}
    for app in first_party_apps:
        metrics = {
            "circular_deps": cycles_per_app.get(app, 0),
            "violations": violations_per_app.get(app, 0),
            "ghost_files": ghosts_per_app.get(app, 0),
        }
        health_scores[app] = calculate_app_health_score(app, metrics, first_party_set)

    # Build nodes
    nodes: list[GraphNode] = []
    for app in first_party_apps:
        nodes.append(
            GraphNode(
                id=app,
                label=app,
                group="first_party",
                health_score=health_scores.get(app, 100.0),
                issues=violations_per_app.get(app, 0) + cycles_per_app.get(app, 0),
            )
        )

    # Build edges from imports
    edges: list[GraphEdge] = []
    edge_map: Dict[tuple[str, str], int] = defaultdict(int)

    for imp in imports:
        if imp.classification == "first_party":
            src_app = _get_app_name(imp.importer)
            tgt_app = _get_app_name(imp.imported)
            if src_app != tgt_app and src_app in first_party_set and tgt_app in first_party_set:
                edge_key = (src_app, tgt_app)
                edge_map[edge_key] += 1

    for (src, tgt), count in edge_map.items():
        conn_type, _, _ = classify_connection(src, tgt, first_party_set)
        edges.append(
            GraphEdge(
                from_node=src,
                to_node=tgt,
                connection_type=conn_type,
                weight=count,
            )
        )

    return ArchitectureResult(
        nodes=nodes,
        edges=edges,
        coupling_matrix=coupling,
        health_scores=health_scores,
        ghost_files=ghosts,
        circular_dependencies=cycles,
    )
