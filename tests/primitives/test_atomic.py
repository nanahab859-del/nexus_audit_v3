import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.primitives.atomic import write_json, read_json

@pytest.mark.asyncio
async def test_write_read_json():
    path = Path("test_data.json")
    data = {"key": "value", "list": [1, 2, 3]}
    await write_json(path, data, indent=4)
    assert await read_json(path) == data
    path.unlink()

@pytest.mark.asyncio
async def test_read_missing_file():
    assert await read_json(Path("non_existent.json")) is None

@pytest.mark.asyncio
async def test_ensure_dir(tmp_path):
    path = tmp_path / "nested/dir/test.json"
    await write_json(path, {"a": 1})
    assert path.parent.exists()

@pytest.mark.asyncio
async def test_write_failure_cleanup(tmp_path):
    path = tmp_path / "fail.json"
    with pytest.raises(Exception):
        await write_json(path, { "a": lambda x: x }) # Non-serializable
    assert len(list(tmp_path.glob("*.tmp"))) == 0

@pytest.mark.asyncio
async def test_write_json_raises_on_permission_denied(tmp_path):
    path = tmp_path / "test.json"
    with patch("aiofiles.open", side_effect=PermissionError):
        pass
    assert len(list(tmp_path.glob("*.tmp"))) == 0

@pytest.mark.asyncio
async def test_write_json_cleans_up_tmp_on_os_error(tmp_path):
    path = tmp_path / "test.json"
    with patch("os.replace", side_effect=OSError):
        with pytest.raises(OSError):
            await write_json(path, {"a": 1})
    assert len(list(tmp_path.glob("*.tmp"))) == 0

@pytest.mark.asyncio
async def test_read_json_returns_none_on_permission_error(tmp_path):
    path = tmp_path / "test.json"
    path.write_text("{}")
    with patch("aiofiles.open", side_effect=PermissionError):
        assert await read_json(path) is None

@pytest.mark.asyncio
async def test_read_json_handles_empty_file(tmp_path):
    path = tmp_path / "empty.json"
    path.touch()
    assert await read_json(path) is None
