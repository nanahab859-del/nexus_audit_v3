import pytest
from core.primitives.settings import SettingsManager

@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """
    Override the root configuration directory during test execution
    to guarantee zero cross-contamination with the local environment.
    """
    original_init = SettingsManager.__init__
    
    def mock_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._workspace_path = tmp_path / ".nexus_audit" / "workspace.json"
        self._projects_dir = tmp_path / ".nexus_audit" / "projects"
        self._workspace_path.parent.mkdir(parents=True, exist_ok=True)
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        
    monkeypatch.setattr(SettingsManager, "__init__", mock_init)
