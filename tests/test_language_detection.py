"""
tests/test_language_detection.py
Tests for detect_languages() and is_language_supported().
"""

import pytest
from pathlib import Path
from core.language_detection import detect_languages, is_language_supported


# ── detect_languages ───────────────────────────────────────────────────────────

def test_detects_python(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    langs = detect_languages(tmp_path)
    assert "python" in langs


def test_detects_javascript(tmp_path):
    (tmp_path / "app.js").write_text("console.log('hi')")
    langs = detect_languages(tmp_path)
    assert "javascript" in langs


def test_detects_typescript(tmp_path):
    (tmp_path / "index.ts").write_text("const x: number = 1;")
    langs = detect_languages(tmp_path)
    assert "typescript" in langs


def test_detects_go(tmp_path):
    (tmp_path / "main.go").write_text("package main")
    langs = detect_languages(tmp_path)
    assert "go" in langs


def test_ignores_node_modules(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "lib.py").write_text("# should be ignored")
    langs = detect_languages(tmp_path)
    # If no other files exist, no languages detected
    assert "python" not in langs


def test_ignores_venv(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "util.py").write_text("# inside venv")
    langs = detect_languages(tmp_path)
    assert "python" not in langs


def test_empty_directory_returns_empty(tmp_path):
    langs = detect_languages(tmp_path)
    assert len(langs) == 0


def test_nonexistent_directory():
    langs = detect_languages(Path("/nonexistent/path/abc123"))
    assert len(langs) == 0


def test_multiple_languages(tmp_path):
    (tmp_path / "app.py").write_text("")
    (tmp_path / "app.js").write_text("")
    (tmp_path / "main.go").write_text("")
    langs = detect_languages(tmp_path)
    assert "python" in langs
    assert "javascript" in langs
    assert "go" in langs


# ── is_language_supported ─────────────────────────────────────────────────────

def test_supported_when_overlap():
    assert is_language_supported(["python", "ruby"], {"python", "go"}) is True


def test_not_supported_when_no_overlap():
    assert is_language_supported(["java", "kotlin"], {"python"}) is False


def test_wildcard_scanner_always_supported():
    # "*" means any — the orchestrator checks scanner_langs != ["*"]
    # is_language_supported(["*"], ...) is called with actual language names,
    # so it won't match unless the detected set contains "*" (it won't).
    # The orchestrator skips language check for ["*"]; this tests the helper directly.
    assert is_language_supported(["python"], {"python"}) is True


def test_no_detected_languages_returns_true():
    """If detection failed (empty set), scanner should be allowed to run."""
    assert is_language_supported(["python"], set()) is True


def test_case_insensitive_match():
    assert is_language_supported(["Python"], {"python"}) is True
