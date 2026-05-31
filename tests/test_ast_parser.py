"""Tests for core.ast_parser module."""

import pytest
from core.ast_parser import (
    parse_project_imports,
    classify_import,
    get_first_party_apps,
)
from core.file_discovery import DiscoveredFile


@pytest.mark.asyncio
async def test_classify_import_first_party():
    """Test that first-party apps are correctly classified."""
    first_party = {"core", "users", "products"}

    assert classify_import("core.models", first_party) == "first_party"
    assert classify_import("users.views", first_party) == "first_party"
    assert classify_import("products.serializers", first_party) == "first_party"


@pytest.mark.asyncio
async def test_classify_import_django():
    """Test that Django imports are correctly classified."""
    first_party = {"core"}

    assert classify_import("django.db", first_party) == "django"
    assert classify_import("django.http", first_party) == "django"
    assert classify_import("django", first_party) == "django"


@pytest.mark.asyncio
async def test_classify_import_stdlib():
    """Test that stdlib imports are correctly classified."""
    first_party = {"core"}

    assert classify_import("os", first_party) == "stdlib"
    assert classify_import("sys", first_party) == "stdlib"
    assert classify_import("pathlib", first_party) == "stdlib"
    assert classify_import("asyncio", first_party) == "stdlib"


@pytest.mark.asyncio
async def test_classify_import_third_party():
    """Test that unknown imports are classified as third_party."""
    first_party = {"core"}

    assert classify_import("requests", first_party) == "third_party"
    assert classify_import("numpy", first_party) == "third_party"
    assert classify_import("pydantic", first_party) == "third_party"


@pytest.mark.asyncio
async def test_classify_import_empty():
    """Test edge case with empty module name."""
    first_party = {"core"}
    assert classify_import("", first_party) == "third_party"


@pytest.mark.asyncio
async def test_get_first_party_apps_empty(tmp_path):
    """Test first-party app detection with empty project."""
    discovered = []
    apps = get_first_party_apps(tmp_path, discovered)
    assert isinstance(apps, set)
    # Empty project should have no first-party apps
    assert len(apps) == 0


@pytest.mark.asyncio
async def test_get_first_party_apps_with_markers(tmp_path):
    """Test first-party app detection with Django markers (models.py, views.py)."""
    # Create app directories with markers
    core_app = tmp_path / "core"
    core_app.mkdir()
    (core_app / "models.py").touch()

    users_app = tmp_path / "users"
    users_app.mkdir()
    (users_app / "views.py").touch()

    # Create fake discovered files
    discovered = [
        DiscoveredFile(path=tmp_path / "core" / "models.py", relative="core/models.py", language="python", size_bytes=0),
        DiscoveredFile(path=tmp_path / "users" / "views.py", relative="users/views.py", language="python", size_bytes=0),
    ]

    apps = get_first_party_apps(tmp_path, discovered)
    assert "core" in apps
    assert "users" in apps


@pytest.mark.asyncio
async def test_parse_project_imports_simple(tmp_path):
    """Test import parsing with simple project."""
    # Create a simple Python file with imports
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()

    models_file = app_dir / "models.py"
    models_file.write_text("""
import os
import django
from myapp.utils import helper
from requests import get
""")

    discovered = [
        DiscoveredFile(path=tmp_path / "myapp" / "models.py", relative="myapp/models.py", language="python", size_bytes=0),
    ]

    imports = parse_project_imports(tmp_path, discovered)

    # Should have 4 imports
    assert len(imports) >= 3

    # Check classifications
    import_dict = {imp.imported: imp.classification for imp in imports}
    assert import_dict["os"] == "stdlib"
    assert import_dict["django"] == "django"
    # "requests" should be third_party (it will be "requests.get" from the from_import)
    assert any("requests" in imp.imported and imp.classification == "third_party" for imp in imports)


@pytest.mark.asyncio
async def test_parse_project_imports_syntax_error(tmp_path):
    """Test that syntax errors are handled gracefully."""
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()

    # Create file with syntax error
    bad_file = app_dir / "bad.py"
    bad_file.write_text("""
import os
def broken syntax here:
""")

    discovered = [
        DiscoveredFile(path=tmp_path / "myapp" / "bad.py", relative="myapp/bad.py", language="python", size_bytes=0),
    ]

    # Should not raise, just skip the bad file
    imports = parse_project_imports(tmp_path, discovered)
    assert isinstance(imports, list)


@pytest.mark.asyncio
async def test_parse_project_imports_from_import(tmp_path):
    """Test parsing of 'from ... import' statements."""
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()

    file = app_dir / "views.py"
    file.write_text("""
from django.shortcuts import render
from myapp.models import User, Product
from os.path import join
""")

    discovered = [
        DiscoveredFile(path=tmp_path / "myapp" / "views.py", relative="myapp/views.py", language="python", size_bytes=0),
    ]

    imports = parse_project_imports(tmp_path, discovered)

    # Should have imports
    assert len(imports) > 0
    # Check that from_import type is recorded
    assert any(imp.import_type == "from_import" for imp in imports)


@pytest.mark.asyncio
async def test_parse_project_imports_wildcard(tmp_path):
    """Test parsing of wildcard imports."""
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()

    file = app_dir / "utils.py"
    file.write_text("""
from os.path import *
from django import *
""")

    discovered = [
        DiscoveredFile(path=tmp_path / "myapp" / "utils.py", relative="myapp/utils.py", language="python", size_bytes=0),
    ]

    imports = parse_project_imports(tmp_path, discovered)

    # Should have wildcard imports recorded
    assert any(imp.import_type == "from_import_star" for imp in imports)
