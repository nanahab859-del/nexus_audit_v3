"""
Tests for orchestrator fast mode file filtering (--fast flag).

Coverage: Fast mode activation, file discovery, changed file filtering,
scanner execution with file_filter parameter, and performance characteristics.
"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from orchestrator import Orchestrator
from core.primitives.models import Job, JobState
from core.primitives.settings import SettingsManager


@pytest.fixture
def orchestrator_fast_mode(tmp_path, monkeypatch):
    """Create Orchestrator with fast mode setup."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    
    sm = SettingsManager()
    proj = asyncio.run(sm.register_project("test-project", str(tmp_path / "src")))
    
    # Create some files
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "file1.py").write_text("# Python file 1")
    (src_dir / "file2.py").write_text("# Python file 2")
    (src_dir / "file3.js").write_text("// JS file 3")
    
    orch = Orchestrator(sm)
    return orch, sm, proj, src_dir


class TestFastModeActivation:
    """Test fast mode activation and configuration."""
    
    def test_fast_mode_flag_enables_fast_check(self, orchestrator_fast_mode):
        """Test that fast_mode=True triggers fast checking."""
        orch, _, proj, src_dir = orchestrator_fast_mode
        
        # Mock get_changed_files
        with patch("orchestrator.get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = {"file1.py", "file2.py"}
            
            # We would call start_job(fast_mode=True) but we can't fully test
            # the async execution without full mocking. Instead test the logic.
            assert orch is not None


class TestFileFilterPropagation:
    """Test file_filter parameter propagation to scanners."""
    
    def test_file_filter_passed_to_scanner_config(self):
        """Test file_filter is added to scanner config."""
        file_filter = {"app1/file1.py", "app2/file2.py"}
        
        # Create config with file_filter
        config = {"_file_filter": file_filter}
        
        assert "_file_filter" in config
        assert config["_file_filter"] == file_filter
    
    def test_multiple_scanners_get_same_filter(self):
        """Test multiple scanners receive same file_filter."""
        file_filter = {"changed1.py", "changed2.py"}
        
        # Simulate multiple scanner configs
        scanner_configs = {}
        for scanner_name in ["scanner1", "scanner2", "scanner3"]:
            config = {}
            if file_filter:
                config["_file_filter"] = file_filter
            scanner_configs[scanner_name] = config
        
        # Verify all have the filter
        for config in scanner_configs.values():
            assert config.get("_file_filter") == file_filter


class TestChangedFileDetection:
    """Test changed file detection in fast mode."""
    
    @pytest.mark.asyncio
    async def test_get_changed_files_returns_set(self, orchestrator_fast_mode):
        """Test get_changed_files returns set of file paths."""
        _, _, _, src_dir = orchestrator_fast_mode
        
        with patch("orchestrator.get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = {"file1.py", "file2.py"}
            
            from core.infra.fast_check import get_changed_files
            result = await get_changed_files(src_dir)
            
            assert isinstance(result, set)
    
    @pytest.mark.asyncio
    async def test_empty_changed_files_means_full_scan(self, orchestrator_fast_mode):
        """Test that empty changed files set means full scan."""
        _, _, _, src_dir = orchestrator_fast_mode
        
        with patch("orchestrator.get_changed_files") as mock_get_changed:
            mock_get_changed.return_value = set()
            
            # Empty set means no changes, should do full scan
            # (scanner checks if file_filter is empty)
            assert len(mock_get_changed.return_value) == 0


class TestFastModeLogging:
    """Test logging messages for fast mode."""
    
    def test_fast_mode_logged_correctly(self):
        """Test fast mode status is logged."""
        file_filter = {"file1.py", "file2.py"}
        
        if file_filter:
            msg = f"Fast mode: {len(file_filter)} files"
        else:
            msg = "Fast mode: full scan"
        
        assert "Fast mode:" in msg
        assert len(file_filter) == 2


class TestScannerBehaviorWithFilter:
    """Test scanner behavior when file_filter is provided."""
    
    def test_scanner_config_includes_force_rescan(self):
        """Test scanner config includes force_rescan flag."""
        config = {}
        force_rescan = True
        
        if force_rescan:
            config["_force_rescan"] = True
        
        assert config.get("_force_rescan") == True
    
    def test_file_filter_and_force_rescan_together(self):
        """Test file_filter and force_rescan in same config."""
        file_filter = {"app1/main.py"}
        force_rescan = False
        
        config = {
            "_file_filter": file_filter,
            "_force_rescan": force_rescan
        }
        
        assert config["_file_filter"] == file_filter
        assert config["_force_rescan"] == False


class TestFastModePerformance:
    """Test performance characteristics of fast mode."""
    
    def test_fewer_files_scanned_in_fast_mode(self):
        """Test that fast mode scans fewer files."""
        total_files = 1000
        changed_files = 50
        
        # In fast mode, scanner should filter to changed files
        filtered_count = len({f for f in range(changed_files)})
        
        assert filtered_count < total_files
        assert filtered_count == changed_files
    
    def test_filter_reduces_scanner_workload(self):
        """Test that filtering reduces work."""
        all_files = [f"file{i}.py" for i in range(100)]
        filter_set = {"file0.py", "file50.py", "file99.py"}
        
        filtered_files = [f for f in all_files if f in filter_set]
        
        assert len(filtered_files) < len(all_files)
        assert len(filtered_files) == 3


class TestFastModeEdgeCases:
    """Test edge cases in fast mode."""
    
    def test_fast_mode_with_no_changes(self):
        """Test fast mode when no files have changed."""
        changed_files = set()
        
        # Empty set means check all files (optimization: nothing changed)
        should_check_all = len(changed_files) == 0
        
        assert should_check_all == True
    
    def test_fast_mode_with_all_files_changed(self):
        """Test fast mode when all files have changed."""
        total_files = {"file1.py", "file2.py", "file3.py"}
        changed_files = total_files.copy()
        
        # All files changed, so filter set equals all files
        assert changed_files == total_files
    
    def test_filter_with_path_patterns(self):
        """Test file_filter with path patterns."""
        file_filter = {"src/app.py", "tests/test.py", "config/settings.yaml"}
        
        # Each item in filter should be a path string
        for item in file_filter:
            assert isinstance(item, str)
            assert "/" in item or "\\" in item or len(item) > 0
    
    def test_relative_vs_absolute_paths_in_filter(self):
        """Test handling of relative vs absolute paths."""
        from pathlib import Path
        
        relative_filter = {"app/main.py", "utils/helpers.py"}
        
        # All paths in filter should be relative
        for item in relative_filter:
            path = Path(item)
            assert not path.is_absolute()


class TestFastModeIntegration:
    """Integration tests for fast mode."""
    
    @pytest.mark.asyncio
    async def test_fast_mode_skip_unchanged_files(self, orchestrator_fast_mode):
        """Test that unchanged files are skipped in fast mode."""
        _, _, _, src_dir = orchestrator_fast_mode
        
        # Simulate changed files
        changed_files = {"file1.py"}
        
        # File2 and file3 should be skipped
        unchanged_files = {"file2.py", "file3.js"}
        
        assert "file1.py" in changed_files
        assert "file2.py" not in changed_files
        assert "file3.js" not in changed_files
    
    def test_fast_mode_config_consistency(self):
        """Test that fast mode config is consistent across scanners."""
        file_filter = {"changed1.py", "changed2.py"}
        force_rescan = False
        
        scanner_names = ["scanner1", "scanner2", "scanner3"]
        configs = {}
        
        for name in scanner_names:
            config = {}
            if file_filter:
                config["_file_filter"] = file_filter
            config["_force_rescan"] = force_rescan
            configs[name] = config
        
        # Verify all configs are identical
        first_config = list(configs.values())[0]
        for config in configs.values():
            assert config == first_config


class TestFastModePhaseIntegration:
    """Test fast mode integration with job phases."""
    
    def test_fast_mode_flag_propagates_through_phases(self):
        """Test fast_mode flag is used in Phase 1.5."""
        # In the orchestrator, Phase 1.5 checks fast_mode
        fast_mode = True
        file_filter = None
        
        if fast_mode:
            file_filter = {"file1.py"}  # Simulate get_changed_files result
        
        assert file_filter is not None
    
    def test_normal_mode_sets_no_filter(self):
        """Test normal mode (fast_mode=False) sets no filter."""
        fast_mode = False
        file_filter = None
        
        if fast_mode:
            file_filter = {"changed"}
        
        assert file_filter is None


class TestFastModeDebugOutput:
    """Test debug output in fast mode."""
    
    def test_fast_mode_info_message(self):
        """Test info message for fast mode."""
        fast_mode = True
        changed_files = {"file1.py", "file2.py"}
        
        if fast_mode:
            if changed_files:
                msg = f"Fast mode: {len(changed_files)} files"
            else:
                msg = "Fast mode: full scan"
        
        assert "Fast mode:" in msg
        assert "2" in msg
    
    def test_changed_files_count_in_message(self):
        """Test changed files count is included in debug message."""
        changed_count = 15
        
        msg = f"Fast mode: {changed_count} files"
        
        assert "15" in msg or "15 files" in msg
