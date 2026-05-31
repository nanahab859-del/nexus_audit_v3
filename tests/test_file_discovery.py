"""Tests for core.file_discovery."""

from pathlib import Path
from core.file_discovery import discover


def test_discover_empty_directory(tmp_path: Path) -> None:
    """Test discover() on empty directory returns empty list."""
    result = discover(tmp_path)
    assert result == []


def test_discover_simple_project(tmp_path: Path) -> None:
    """Test discover() finds Python files."""
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "lib.py").write_text("def foo(): pass")
    (tmp_path / "data.json").write_text('{"key": "value"}')

    result = discover(tmp_path)
    assert len(result) == 3
    names = {f.relative for f in result}
    assert "main.py" in names
    assert "lib.py" in names
    assert "data.json" in names


def test_discover_classifies_languages(tmp_path: Path) -> None:
    """Test language classification."""
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "app.js").write_text("console.log()")
    (tmp_path / "README.md").write_text("# Test")

    result = discover(tmp_path)
    files_by_name = {f.relative: f for f in result}

    assert files_by_name["main.py"].language == "python"
    assert files_by_name["app.js"].language == "javascript"
    assert files_by_name["README.md"].language == "markdown"


def test_discover_skips_pyc(tmp_path: Path) -> None:
    """Test that .pyc files are skipped."""
    (tmp_path / "module.py").write_text("x = 1")
    (tmp_path / "module.pyc").write_bytes(b"\x00\x01\x02\x03")  # Binary

    result = discover(tmp_path)
    names = {f.relative for f in result}
    assert "module.py" in names
    assert "module.pyc" not in names


def test_discover_skips_git_dir(tmp_path: Path) -> None:
    """Test that .git/ directory is excluded."""
    (tmp_path / ".git" / "config").parent.mkdir(parents=True)
    (tmp_path / ".git" / "config").write_text("ref: refs/heads/main")
    (tmp_path / "main.py").write_text("x = 1")

    result = discover(tmp_path)
    names = {f.relative for f in result}
    assert "main.py" in names
    assert not any(".git" in n for n in names)


def test_discover_skips_pycache(tmp_path: Path) -> None:
    """Test that __pycache__/ directory is excluded."""
    (tmp_path / "__pycache__" / "module.pyc").parent.mkdir(parents=True)
    (tmp_path / "__pycache__" / "module.pyc").write_bytes(b"\x00\x01")
    (tmp_path / "module.py").write_text("x = 1")

    result = discover(tmp_path)
    names = {f.relative for f in result}
    assert "module.py" in names
    assert not any("__pycache__" in n for n in names)


def test_discover_skips_binary_files(tmp_path: Path) -> None:
    """Test that binary files are skipped."""
    (tmp_path / "text.txt").write_text("hello world")
    # Create binary file with null bytes
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03\x00binary_data")

    result = discover(tmp_path)
    names = {f.relative for f in result}
    assert "text.txt" in names
    assert "binary.bin" not in names


def test_discover_respects_gitignore(tmp_path: Path) -> None:
    """Test that .gitignore is respected."""
    (tmp_path / ".gitignore").write_text("*.log\n__pycache__/\n")
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "debug.log").write_text("log data")
    (tmp_path / "data.txt").write_text("data")

    result = discover(tmp_path, respect_gitignore=True)
    names = {f.relative for f in result}
    assert "main.py" in names
    assert "data.txt" in names
    assert "debug.log" not in names


def test_discover_ignores_gitignore_when_flag_false(tmp_path: Path) -> None:
    """Test that respect_gitignore=False ignores .gitignore."""
    (tmp_path / ".gitignore").write_text("*.log\n")
    (tmp_path / "debug.log").write_text("log data")

    result = discover(tmp_path, respect_gitignore=False)
    names = {f.relative for f in result}
    assert "debug.log" in names


def test_discover_shebang_override(tmp_path: Path) -> None:
    """Test that shebang overrides extension classification."""
    # Create a .sh file with Python shebang
    sh_file = tmp_path / "script.sh"
    sh_file.write_text("#!/usr/bin/env python3\nprint('hello')")

    result = discover(tmp_path)
    assert len(result) == 1
    assert result[0].language == "python"


def test_discover_preserves_sizes(tmp_path: Path) -> None:
    """Test that file sizes are recorded."""
    content = "x = 1\n"
    file_path = tmp_path / "file.py"
    file_path.write_text(content)
    actual_size = file_path.stat().st_size

    result = discover(tmp_path)
    assert len(result) == 1
    assert result[0].size_bytes == actual_size


def test_discover_sorts_deterministically(tmp_path: Path) -> None:
    """Test that results are sorted by relative path."""
    (tmp_path / "z.py").write_text("x = 1")
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "m.py").write_text("x = 1")

    result = discover(tmp_path)
    relatives = [f.relative for f in result]
    assert relatives == ["a.py", "m.py", "z.py"]


def test_discover_nested_structure(tmp_path: Path) -> None:
    """Test discover() on nested directory structure."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1")
    (tmp_path / "src" / "lib").mkdir()
    (tmp_path / "src" / "lib" / "utils.py").write_text("def f(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")

    result = discover(tmp_path)
    relatives = sorted(f.relative for f in result)
    assert relatives == ["src/lib/utils.py", "src/main.py", "tests/test_main.py"]


def test_discovered_file_has_absolute_path(tmp_path: Path) -> None:
    """Test that DiscoveredFile.path is absolute."""
    (tmp_path / "file.py").write_text("x = 1")

    result = discover(tmp_path)
    assert len(result) == 1
    assert result[0].path.is_absolute()
    assert result[0].path.name == "file.py"
