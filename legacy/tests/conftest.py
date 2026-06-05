# conftest.py – common fixtures for the test suite
import json
import shutil
import os
from pathlib import Path
import tempfile
import pytest
import pytest_asyncio
from core.settings import Settings, load as load_settings
from core.events import EventBus

@pytest.fixture(autouse=True, scope="session")
def clean_audit_files():
    """Remove any leftover audit files before the test session starts."""
    # Delete the main audit result file if it exists
    audit_file = Path("audit_data_complete.json")
    if audit_file.exists():
        audit_file.unlink()
    # Remove the audit history directory if it exists
    history_dir = Path("audit_history")
    if history_dir.is_dir():
        shutil.rmtree(history_dir, ignore_errors=True)
    # No return needed
    yield
    # Optionally cleanup after tests as well
    if audit_file.exists():
        audit_file.unlink()
    if history_dir.is_dir():
        shutil.rmtree(history_dir, ignore_errors=True)

@pytest.fixture(scope="session")
def temp_project():
    """Create a temporary project directory with minimal files used by many tests."""
    tmp_dir = Path(tempfile.mkdtemp())
    # Minimal settings.json
    settings = {
        "project_path": str(tmp_dir),
        "api_key": None,
        "ai_enabled": False,
        "scanners": {"bandit": False, "vulture": False},
        "scanner_configs": {},
        "ui": {},
    }
    (tmp_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)

@pytest.fixture
def settings(temp_project):
    return load_settings(temp_project / "settings.json")

@pytest_asyncio.fixture
async def event_bus():
    """Create an EventBus instance for async tests."""
    return EventBus()
