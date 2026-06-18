import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from core.primitives.events import EventBus

class DummyBus(EventBus):
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass
    async def publish_finding(self, *args, **kwargs): pass
    async def start(self): pass
    async def stop(self): pass

@pytest.mark.asyncio
async def test_extreme_django_settings(tmp_path):
    from plugins.security.django_settings_plugin import DjangoSettingsScanner
    bus = DummyBus()
    scanner = DjangoSettingsScanner({}, bus)
    
    assert await scanner._build_args(tmp_path, {}) == []
    
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("DEBUG=True\nSECURE_HSTS_SECONDS=0")
    # This will trigger missing SECRET_KEY (91) and other settings (100)
    findings = await scanner.scan(tmp_path, {}, bus)
    assert len(findings) > 0
    
    # Trigger Exception reading settings
    settings_file.chmod(0o000)
    # Note: On some systems, root ignores chmod. But we can mock read_text
    with patch("pathlib.Path.read_text", side_effect=PermissionError):
        await scanner.scan(tmp_path, {}, bus)
    settings_file.chmod(0o644)

@pytest.mark.asyncio
async def test_extreme_secretscrub(tmp_path):
    from plugins.security.secretscrub_plugin import SecretScrubScanner
    bus = DummyBus()
    scanner = SecretScrubScanner({}, bus)
    
    assert await scanner._build_args(tmp_path, {}) == []
    
    f1 = tmp_path / "ignored.txt"
    f1.write_text("test")
    
    # Large file > 1MB
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"0" * (1024 * 1024 + 10))
    
    # Low entropy base64
    b64_file = tmp_path / "b64.txt"
    b64_file.write_text("AAAAA") # very low entropy
    
    # File that raises exception
    err_file = tmp_path / "err.txt"
    err_file.write_text("test")
    
    with patch("plugins.security.secretscrub_plugin.discover", return_value=[
        type("FileNode", (), {"absolute_path": err_file, "relative_path": "err.txt"}),
        type("FileNode", (), {"absolute_path": large_file, "relative_path": "large.txt"}),
        type("FileNode", (), {"absolute_path": b64_file, "relative_path": "b64.txt"}),
        type("FileNode", (), {"absolute_path": f1, "relative_path": "ignored.txt"}),
    ]):
        with patch.object(SecretScrubScanner, '_entropy_score', return_value=1.0):
            with patch("pathlib.Path.read_text", side_effect=[PermissionError, "base64 = AAAAA", "test", "test"]):
                await scanner.scan(tmp_path, {"exclude_paths": ["ignored.txt"]}, bus)

@pytest.mark.asyncio
async def test_extreme_trufflehog(tmp_path):
    from plugins.security.trufflehog_plugin import TruffleHogScanner
    bus = DummyBus()
    scanner = TruffleHogScanner({}, bus)
    
    (tmp_path / ".git").mkdir()
    args = await scanner._build_args(tmp_path, {"exclude_paths": ["venv"]})
    assert "git" in args
    assert "--exclude-paths" in args
    
    assert scanner._parse_output("{invalid json}\n") == []

