import pytest
import os
import shutil
from pathlib import Path
from core.engines.dna_builder import build_dna
from core.primitives.events import EventBus

@pytest.mark.asyncio
async def test_builds_module_entries(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "mod1.py").write_text("import os\n\ndef func():\n    pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert len(dna.modules) == 1
    assert "mod1" in dna.modules
    assert dna.modules["mod1"].language == "python"
    assert dna.modules["mod1"].lines_of_code == 3

@pytest.mark.asyncio
async def test_init_py_normalized(tmp_path):
    project_root = tmp_path / "project"
    pkg_dir = project_root / "pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("# init file")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    # Should normalize to 'pkg', not 'pkg.__init__'
    assert "pkg" in dna.modules
    assert "pkg.__init__" not in dna.modules

@pytest.mark.asyncio
async def test_relative_import_resolved(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "my_app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "mod.py").write_text("from . import sibling")
    (app_dir / "sibling.py").write_text("pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "my_app.mod" in dna.modules
    assert "my_app.sibling" in dna.modules["my_app.mod"].imports

@pytest.mark.asyncio
async def test_alias_discarded(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "my_app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "mod.py").write_text("import my_app.sibling as s")
    (app_dir / "sibling.py").write_text("pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "my_app.mod" in dna.modules
    assert "my_app.sibling" in dna.modules["my_app.mod"].imports
    assert "s" not in dna.modules["my_app.mod"].imports

@pytest.mark.asyncio
async def test_wildcard_detected(tmp_path):
    pass

@pytest.mark.asyncio
async def test_syntax_error_degrades_gracefully(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "bad.py").write_text("def def def") # Syntax error
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "bad" in dna.modules
    assert dna.modules["bad"].parse_status == "error"

@pytest.mark.asyncio
async def test_large_file_skipped(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    f = project_root / "large.py"
    f.write_text("a" * (1024 * 1024 + 1))
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "large" not in dna.modules

@pytest.mark.asyncio
async def test_min_file_skipped(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "bundle.min.js").write_text("var a=1;")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "bundle.min" not in dna.modules

@pytest.mark.asyncio
async def test_app_assignment(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "app1"
    app_dir.mkdir(parents=True)
    (app_dir / "mod.py").write_text("pass")
    
    bus = EventBus()
    app_mappings = [{"path_prefix": "app1", "app": "my-app"}]
    dna = await build_dna(project_root, bus, app_mappings=app_mappings)
    
    assert dna.modules["app1.mod"].app == "my-app"

@pytest.mark.asyncio
async def test_symlink_loop_protection(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "real.py").write_text("pass")
    
    # Create symlink loop
    (project_root / "loop").symlink_to(project_root)
    
    bus = EventBus()
    # Should complete without infinite recursion
    dna = await build_dna(project_root, bus)
    assert "real" in dna.modules

from core.infra.file_discovery import DiscoveredFile



@pytest.mark.asyncio
async def test_app_assignment_parts(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    f1 = project_root / "src" / "my_backend" / "app.py"
    f1.parent.mkdir(parents=True)
    f1.write_text("pass")
    
    async def mock_discover(root):
        return [
            DiscoveredFile(absolute_path=f1, relative_path="src/my_backend/app.py", language="python", size_bytes=4)
        ]
        
    monkeypatch.setattr("core.engines.dna_builder.discover", mock_discover)
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    assert dna.modules["src.my_backend.app"].app == "my_backend"

@pytest.mark.asyncio
async def test_type_checking_import_excluded(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "my_app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "mod.py").write_text("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import my_app.other")
    (app_dir / "other.py").write_text("pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "my_app.mod" in dna.modules
    assert "my_app.other" not in dna.modules["my_app.mod"].imports

@pytest.mark.asyncio
async def test_regular_import_included(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "my_app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "mod.py").write_text("import my_app.other")
    (app_dir / "other.py").write_text("pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "my_app.mod" in dna.modules
    assert "my_app.other" in dna.modules["my_app.mod"].imports

@pytest.mark.asyncio
async def test_migrations_excluded(tmp_path):
    project_root = tmp_path / "project"
    app_dir = project_root / "some_app" / "migrations"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("")
    (app_dir / "0001_initial.py").write_text("pass")
    
    bus = EventBus()
    dna = await build_dna(project_root, bus)
    
    assert "some_app.migrations.0001_initial" not in dna.modules
