import pytest
from pathlib import Path
from core.infra.language_detection import (
    detect, detect_languages, is_language_supported,
    EXTENSION_MAP, EXACT_MATCH_MAP, LANGUAGE_EXTENSIONS
)

def test_detect_all_extensions():
    for ext, lang in EXTENSION_MAP.items():
        assert detect(f"test{ext}") == lang

def test_detect_all_exact_matches():
    for filename, lang in EXACT_MATCH_MAP.items():
        assert detect(filename) == lang
        assert detect(f"/some/path/{filename}") == lang

def test_detect_case_insensitive():
    assert detect("test.PY") == "python"
    assert detect("TEST.JS") == "javascript"
    assert detect("some.HTML") == "html"

def test_detect_unknown():
    assert detect("unknown.ext") == "unknown"
    assert detect("noextension") == "unknown"

def test_detect_path_vs_string():
    assert detect(Path("test.py")) == "python"
    assert detect("test.py") == "python"

def test_detect_languages_ignores_hidden_and_venv(tmp_path):
    (tmp_path / "test.py").touch()
    
    # Hidden
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "hidden.py").touch()
    
    # venv
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "env.py").touch()
    
    node = tmp_path / "node_modules"
    node.mkdir()
    (node / "test.js").touch()
    
    langs = detect_languages(tmp_path)
    assert langs == {"python"}  # Should only detect the root one

def test_detect_languages_depth(tmp_path):
    d = tmp_path
    for i in range(6):
        d = d / f"dir{i}"
        d.mkdir()
    (d / "deep.go").touch()
    assert "go" not in detect_languages(tmp_path)

def test_detect_languages_non_existent():
    assert detect_languages(Path("/does/not/exist/ever/123")) == set()

def test_detect_languages_permission_error(tmp_path, monkeypatch):
    def mock_rglob(*args, **kwargs):
        raise PermissionError()
    monkeypatch.setattr(Path, "rglob", mock_rglob)
    assert detect_languages(tmp_path) == set()

def test_is_language_supported():
    assert is_language_supported(["python", "javascript"], {"python", "go"}) is True
    assert is_language_supported(["python"], {"go", "rust"}) is False
    assert is_language_supported(["python"], set()) is True
    assert is_language_supported(["PYTHON"], {"python"}) is True
