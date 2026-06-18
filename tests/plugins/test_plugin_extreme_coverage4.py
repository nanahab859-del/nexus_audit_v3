import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from core.primitives.events import EventBus

class DummyBus(EventBus):
    async def publish_progress(self, *args, **kwargs): pass
    async def publish_log(self, *args, **kwargs): pass
    async def publish_finding(self, *args, **kwargs): pass
    async def start(self): pass
    async def stop(self): pass

@pytest.mark.asyncio
async def test_extreme_secretscrub_lines(tmp_path):
    from plugins.security.secretscrub_plugin import SecretScrubScanner
    bus = DummyBus()
    scanner = SecretScrubScanner({}, bus)
    
    # Mock discover to return two files: one excluded, one with low-entropy base64
    class DummyFile:
        def __init__(self, abs_path, rel_path):
            self.absolute_path = abs_path
            self.relative_path = rel_path
            
    f1 = DummyFile(tmp_path / "ignored.txt", "ignored.txt")
    f2 = DummyFile(tmp_path / "valid.txt", "valid.txt")
    
    with patch("plugins.security.secretscrub_plugin.discover", return_value=[f1, f2]):
        with patch("pathlib.Path.stat") as mock_stat:
            # allow size check
            mock_stat.return_value.st_size = 100
            
            # This read_text will be called only for valid.txt because ignored.txt is excluded
            # The base64 pattern is r"(?i)(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)"
            # Wait, the default patterns are returned by self._get_patterns(), let's just use "base64" in a string.
            with patch("pathlib.Path.read_text", return_value="Here is a token: QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB\n"):
                with patch.object(SecretScrubScanner, "_entropy_score", return_value=3.0): # low entropy
                    with patch.object(SecretScrubScanner, "_check_tool", new_callable=AsyncMock, return_value=True):
                        config = {
                            "exclude_paths": ["*ignored.txt"],
                            "patterns": [{"name": "High Entropy Base64", "regex": r"[A-Za-z0-9+/]{30,}"}]
                        }
                        findings = await scanner.scan(tmp_path, config, bus)
                        assert findings == []
