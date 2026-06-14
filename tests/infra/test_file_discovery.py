import pytest
import os
import sys
from pathlib import Path
from core.infra.file_discovery import discover

@pytest.mark.asyncio
async def test_discovers_python_files(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "test1.py").write_text("print('hi')")
    (project_root / "subdir").mkdir()
    (project_root / "subdir/test2.py").write_text("print('hi')")
    
    files = await discover(project_root, respect_gitignore=False)
    assert len(files) == 2
    assert any(f.relative_path == "test1.py" for f in files)
    assert any(f.relative_path == "subdir/test2.py" for f in files)

@pytest.mark.asyncio
async def test_excludes_common_dirs(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    (project_root / ".git/config").write_text("...")
    (project_root / "test.py").write_text("print('hi')")
    
    files = await discover(project_root, respect_gitignore=False)
    assert len(files) == 1
    assert not any(".git" in f.relative_path for f in files)

@pytest.mark.asyncio
async def test_skips_large_files(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    f = project_root / "large.py"
    f.write_text("a" * 1_000_001)
    
    files = await discover(project_root, respect_gitignore=False)
    assert len(files) == 0

@pytest.mark.asyncio
async def test_skips_minified(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app.min.js").write_text("console.log('hi')")
    
    files = await discover(project_root, respect_gitignore=False)
    assert len(files) == 0

@pytest.mark.asyncio
async def test_respects_gitignore(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "ignored.py").write_text("pass")
    (project_root / ".gitignore").write_text("ignored.py")
    
    files = await discover(project_root, respect_gitignore=True)
    assert not any(f.relative_path == "ignored.py" for f in files)

@pytest.mark.asyncio
async def test_symlink_loop(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "real.py").write_text("pass")
    loop_dir = project_root / "loop"
    loop_dir.symlink_to(project_root, target_is_directory=True)
    
    files = await discover(project_root, respect_gitignore=False)
    # the symlink might be resolved if we use os.walk with followlinks?
    # but the logic resolves root_path and checks if in visited
    assert len(files) == 1
    assert files[0].relative_path == "real.py"

@pytest.mark.asyncio
async def test_import_error_pathspec(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pathspec", None)
    
    # Reload file_discovery to trigger ImportError
    import importlib
    import core.infra.file_discovery
    importlib.reload(core.infra.file_discovery)
    
    project_root = tmp_path / "project_no_pathspec"
    project_root.mkdir()
    (project_root / "test.py").write_text("print('hi')")
    (project_root / ".gitignore").write_text("test.py") # Should NOT ignore it since pathspec is none
    
    files = await core.infra.file_discovery.discover(project_root, respect_gitignore=True)
    assert len(files) == 2
    
    # Restore
    importlib.reload(core.infra.file_discovery)

@pytest.mark.asyncio
async def test_exclude_patterns(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "test1.py").write_text("pass")
    (project_root / "test2.py").write_text("pass")
    
    files = await discover(project_root, respect_gitignore=False, exclude_patterns=["*2.py"])
    assert len(files) == 1
    assert files[0].relative_path == "test1.py"

@pytest.mark.asyncio
async def test_oserror_on_stat_and_binary(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "test1.py").write_text("pass")
    (project_root / "test2.py").write_text("pass")
    (project_root / "binary.bin").write_bytes(b"hello\0world")
    
    orig_stat = Path.stat
    def mock_stat(self, *args, **kwargs):
        if self.name == "test1.py":
            raise OSError("no stat for you")
        return orig_stat(self, *args, **kwargs)
        
    orig_open = builtins_open = open
    def mock_open(*args, **kwargs):
        # We need to use string representation of Path since args[0] might be a Path object
        if "test2.py" in str(args[0]):
            raise OSError("no open for you")
        return orig_open(*args, **kwargs)
    
    monkeypatch.setattr(Path, "stat", mock_stat)
    monkeypatch.setattr("builtins.open", mock_open)
    
    files = await discover(project_root, respect_gitignore=False)
    # test1.py fails stat, test2.py fails open, binary.bin fails binary check
    assert len(files) == 0

def test_symlink_protection_duplicate_resolve(tmp_path, monkeypatch):
    from core.infra.file_discovery import _walk_project
    from pathlib import Path
    
    # We monkeypatch Path.resolve to return the same path twice to simulate overlapping symlinks
    original_resolve = Path.resolve
    call_count = 0
    def mock_resolve(self):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            return original_resolve(Path("/"))
        return original_resolve(self)
        
    monkeypatch.setattr(Path, "resolve", mock_resolve)
    
    # Create subdirectories so os.walk loops multiple times
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    
    res = _walk_project(tmp_path, False, [])
