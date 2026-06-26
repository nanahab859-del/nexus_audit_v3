import pytest
from pathlib import Path
from core.mcp.security import _assert_safe_path

def test_sandbox_allows_inside_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    allowed = tmp_path / ".nexus_audit" / "projects" / "test"
    allowed.parent.mkdir(parents=True, exist_ok=True)
    res = _assert_safe_path(str(allowed))
    assert res == allowed.resolve()

def test_sandbox_rejects_outside_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    forbidden = tmp_path / ".ssh" / "id_rsa"
    with pytest.raises(ValueError, match="Path outside allowed sandbox"):
        _assert_safe_path(str(forbidden))

def test_sandbox_rejects_relative_escape(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    sneaky = tmp_path / ".nexus_audit" / ".." / ".." / "etc" / "passwd"
    with pytest.raises(ValueError, match="Path outside allowed sandbox"):
        _assert_safe_path(str(sneaky))
