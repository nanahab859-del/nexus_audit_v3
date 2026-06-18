import asyncio
import pytest
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
from core.infra.source_sync import sync, SyncConfig, SyncError
from core.primitives.events import EventBus

@pytest.mark.asyncio
async def test_disabled():
    path = "/tmp/fake/project"
    config = SyncConfig(enabled=False, local_path=path)
    result = await sync(config)
    assert result == Path(path)

@pytest.mark.asyncio
async def test_explicit_working_dir(tmp_path):
    wd = tmp_path / "explicit_wd"
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("hello")
    
    config = SyncConfig(enabled=True, source_type="local", local_path=str(source), working_dir=str(wd))
    res = await sync(config)
    assert res == wd
    assert (wd / "file.txt").exists()

@pytest.mark.asyncio
async def test_local_copy_with_bus(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("hello")
    (source / ".git").mkdir()
    (source / ".git/config").write_text("...")
    
    bus = EventBus()
    # just create a simple mock for the method
    bus.publish_log = AsyncMock()
    
    config = SyncConfig(enabled=True, source_type="local", local_path=str(source))
    wd = await sync(config, bus=bus)
    
    assert wd.exists()
    assert (wd / "file.txt").exists()
    assert not (wd / ".git").exists()
    bus.publish_log.assert_called_once_with("info", "Copying local files...")

@pytest.mark.asyncio
async def test_remote_clone(tmp_path):
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        mock_exec.return_value = proc
        
        bus = EventBus()
        bus.publish_log = AsyncMock()
        
        config = SyncConfig(
            enabled=True, 
            source_type="remote", 
            remote_url="https://github.com/user/repo.git"
        )
        wd = await sync(config, bus=bus)
        
        assert wd.exists()
        mock_exec.assert_called_once()
        assert "git" in mock_exec.call_args[0]
        assert "clone" in mock_exec.call_args[0]
        bus.publish_log.assert_called_once()
        assert "Cloning" in bus.publish_log.call_args[0][1]

@pytest.mark.asyncio
async def test_token_injection(tmp_path):
    """Token must NOT appear in the git clone process arguments (credential-file approach)."""
    captured_args = []

    async def mock_create_subprocess_exec(*args, **kwargs):
        captured_args.extend(args)
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        os.environ["MY_TOKEN"] = "secret123"
        config = SyncConfig(
            enabled=True,
            source_type="remote",
            remote_url="https://github.com/user/repo.git",
            token_env="MY_TOKEN"
        )
        await sync(config, bus=None)
        del os.environ["MY_TOKEN"]

    # The token must not appear in any subprocess argument
    cmd_str = " ".join(str(a) for a in captured_args)
    assert "secret123" not in cmd_str, "Token leaked into process args"

@pytest.mark.asyncio
async def test_missing_remote_url():
    config = SyncConfig(enabled=True, source_type="remote", remote_url="")
    with pytest.raises(SyncError, match="Remote URL is required"):
        await sync(config)

@pytest.mark.asyncio
async def test_clone_timeout():
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        proc = AsyncMock()
        proc.communicate.side_effect = asyncio.TimeoutError
        mock_exec.return_value = proc
        
        config = SyncConfig(
            enabled=True, 
            source_type="remote", 
            remote_url="https://github.com/user/repo.git"
        )
        with pytest.raises(SyncError, match="Clone timed out"):
            await sync(config)

@pytest.mark.asyncio
async def test_clone_failure_nonzero_exit():
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"permission denied")
        proc.returncode = 128
        mock_exec.return_value = proc
        
        config = SyncConfig(
            enabled=True, 
            source_type="remote", 
            remote_url="https://github.com/user/repo.git"
        )
        with pytest.raises(SyncError, match="Clone failed: permission denied"):
            await sync(config)

@pytest.mark.asyncio
async def test_clone_general_exception():
    """Errors during clone should propagate as SyncError; token never in the URL."""
    async def mock_create_subprocess_exec(*args, **kwargs):
        raise OSError("permission denied")

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        os.environ["MY_TOKEN"] = "secret123"
        config = SyncConfig(
            enabled=True,
            source_type="remote",
            remote_url="https://github.com/user/repo.git",
            token_env="MY_TOKEN"
        )
        with pytest.raises(SyncError) as exc_info:
            await sync(config)
        del os.environ["MY_TOKEN"]

    # The raw URL (which never had the token) should be fine to appear,
    # but the token itself must not leak.
    assert "secret123" not in str(exc_info.value)

@pytest.mark.asyncio
async def test_unsupported_source_type():
    config = SyncConfig(enabled=True, source_type="unknown")
    with pytest.raises(SyncError, match="Unknown source_type"):
        await sync(config)
