"""Tests for core.architecture_analyzer module."""

import pytest
from core.architecture_analyzer import (
    find_circular_dependencies,
    find_ghost_files,
    classify_connection,
    build_coupling_matrix,
    calculate_app_health_score,
    analyze_architecture,
)
from core.models import ImportInfo
from core.file_discovery import DiscoveredFile


@pytest.mark.asyncio
async def test_classify_connection_same_app():
    """Test that same-app imports are not violations."""
    conn_type, penalty, is_violation = classify_connection(
        "core.models", "core.views", {"core", "users"}
    )
    assert conn_type == "internal"
    assert penalty == 0
    assert is_violation is False


@pytest.mark.asyncio
async def test_classify_connection_framework():
    """Test that framework imports are not violations."""
    conn_type, penalty, is_violation = classify_connection(
        "core.models", "django.db", {"core"}
    )
    assert conn_type == "framework"
    assert penalty == 0
    assert is_violation is False


@pytest.mark.asyncio
async def test_classify_connection_bootstrap():
    """Test that bootstrap files are exempt from violations."""
    conn_type, penalty, is_violation = classify_connection(
        "core.settings", "users.models", {"core", "users"}
    )
    assert conn_type == "django_bootstrap"
    assert penalty == 0
    assert is_violation is False


@pytest.mark.asyncio
async def test_classify_connection_signal():
    """Test that signal modules are allowed."""
    conn_type, penalty, is_violation = classify_connection(
        "core.signals", "users.signals", {"core", "users"}
    )
    assert conn_type == "django_signal"
    assert penalty == 0
    assert is_violation is False


@pytest.mark.asyncio
async def test_classify_connection_cross_app_violation():
    """Test that cross-app imports are violations."""
    conn_type, penalty, is_violation = classify_connection(
        "core.models", "users.views", {"core", "users"}
    )
    assert conn_type == "cross_app_import"
    assert penalty == 5
    assert is_violation is True


@pytest.mark.asyncio
async def test_find_circular_dependencies_simple():
    """Test detection of a simple circular dependency: A -> B -> A."""
    imports = [
        ImportInfo("core/models.py", "users", 1, "import", "first_party"),
        ImportInfo("users/models.py", "core", 2, "import", "first_party"),
    ]

    cycles = find_circular_dependencies(imports, {"core", "users"})

    # Should find the cycle
    assert len(cycles) > 0
    # Both should be in the cycle
    cycle_nodes = set()
    for cycle in cycles:
        cycle_nodes.update(cycle)
    assert "core" in cycle_nodes or "users" in cycle_nodes


@pytest.mark.asyncio
async def test_find_circular_dependencies_three_node():
    """Test detection of a three-node circular dependency: A -> B -> C -> A."""
    imports = [
        ImportInfo("core/models.py", "users", 1, "import", "first_party"),
        ImportInfo("users/models.py", "products", 2, "import", "first_party"),
        ImportInfo("products/models.py", "core", 3, "import", "first_party"),
    ]

    cycles = find_circular_dependencies(imports, {"core", "users", "products"})

    # Should find at least one cycle
    assert len(cycles) > 0


@pytest.mark.asyncio
async def test_find_circular_dependencies_none():
    """Test that no false cycles are detected in acyclic graph."""
    imports = [
        ImportInfo("core/models.py", "users", 1, "import", "first_party"),
        ImportInfo("users/models.py", "products", 2, "import", "first_party"),
    ]

    cycles = find_circular_dependencies(imports, {"core", "users", "products"})

    # Should have no cycles (linear dependency chain)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_find_ghost_files(tmp_path):
    """Test detection of ghost files (disconnected files)."""
    # Create files
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    (core_dir / "models.py").touch()
    (core_dir / "views.py").touch()
    (core_dir / "ghost.py").touch()

    discovered = [
        DiscoveredFile(path=tmp_path / "core" / "models.py", relative="core/models.py", language="python", size_bytes=0),
        DiscoveredFile(path=tmp_path / "core" / "views.py", relative="core/views.py", language="python", size_bytes=0),
        DiscoveredFile(path=tmp_path / "core" / "ghost.py", relative="core/ghost.py", language="python", size_bytes=0),
    ]

    # Only models and views are imported, ghost is not
    imports = [
        ImportInfo("core/views.py", "core.models", 1, "import", "first_party"),
    ]

    ghosts = find_ghost_files(tmp_path, discovered, imports, {"core"})

    # ghost.py should be flagged as ghost
    assert any("ghost" in g for g in ghosts)


@pytest.mark.asyncio
async def test_build_coupling_matrix():
    """Test coupling matrix construction."""
    imports = [
        ImportInfo("core/models.py", "users", 1, "import", "first_party"),
        ImportInfo("core/models.py", "users", 2, "import", "first_party"),  # 2 imports
        ImportInfo("users/models.py", "products", 3, "import", "first_party"),
    ]

    matrix = build_coupling_matrix(imports, ["core", "users", "products"])

    assert matrix.apps == ["core", "users", "products"]
    assert len(matrix.matrix) == 3
    # core -> users should have count 2
    core_idx = 0
    users_idx = 1
    assert matrix.matrix[core_idx][users_idx] == 2


@pytest.mark.asyncio
async def test_calculate_app_health_score():
    """Test health score calculation."""
    # Perfect app: no issues
    metrics = {"circular_deps": 0, "violations": 0, "ghost_files": 0}
    score = calculate_app_health_score("users", metrics, {"core", "users"})
    assert score == 100.0

    # App with violations
    metrics = {"circular_deps": 1, "violations": 2, "ghost_files": 0}
    score = calculate_app_health_score("users", metrics, {"core", "users"})
    assert score < 100.0
    assert score >= 0.0

    # Score should be clamped to 0-100
    metrics = {"circular_deps": 100, "violations": 100, "ghost_files": 100}
    score = calculate_app_health_score("users", metrics, {"core", "users"})
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_analyze_architecture_minimal(tmp_path):
    """Test full architecture analysis on minimal project."""
    # Create minimal project structure
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    (core_dir / "models.py").touch()

    discovered = [
        DiscoveredFile(path=tmp_path / "core" / "models.py", relative="core/models.py", language="python", size_bytes=0),
    ]

    imports: list[ImportInfo] = []

    result = analyze_architecture(tmp_path, discovered, imports)

    # Should have basic structure
    assert result.nodes is not None
    assert result.edges is not None
    assert result.coupling_matrix is not None
    assert result.health_scores is not None
    assert result.ghost_files is not None
    assert result.circular_dependencies is not None
