import pytest
from pathlib import Path
from core.atomic import write_json, read_json
import json


@pytest.mark.asyncio
async def test_write_and_read_round_trip(tmp_path: Path) -> None:
    """Test write → read round-trip preserves data."""
    data = {"key": "value", "number": 42}
    path = tmp_path / "test.json"

    await write_json(path, data)
    result = await read_json(path)

    assert result == data


@pytest.mark.asyncio
async def test_write_creates_file(tmp_path: Path) -> None:
    """Test that write_json creates the file."""
    data = {"test": "data"}
    path = tmp_path / "test.json"

    await write_json(path, data)

    assert path.exists()


@pytest.mark.asyncio
async def test_write_cleans_up_tmp(tmp_path: Path) -> None:
    """Test that .tmp file is cleaned up after success."""
    data = {"test": "data"}
    path = tmp_path / "test.json"

    await write_json(path, data)

    tmp_path_file = path.with_suffix(".tmp")
    assert not tmp_path_file.exists()


@pytest.mark.asyncio
async def test_read_missing_file() -> None:
    """Test reading missing file returns None."""
    path = Path("/nonexistent/file.json")
    result = await read_json(path)
    assert result is None


@pytest.mark.asyncio
async def test_read_corrupt_file(tmp_path: Path) -> None:
    """Test reading corrupt file raises JSONDecodeError."""
    path = tmp_path / "corrupt.json"
    path.write_text("{ invalid json")

    with pytest.raises(json.JSONDecodeError):
        await read_json(path)


@pytest.mark.asyncio
async def test_write_json_with_list(tmp_path: Path) -> None:
    """Test writing list data."""
    data = [1, 2, 3, "four"]
    path = tmp_path / "test.json"

    await write_json(path, data)
    result = await read_json(path)

    assert result == data


@pytest.mark.asyncio
async def test_write_json_formats_with_indent(tmp_path: Path) -> None:
    """Test that JSON is formatted with indent."""
    data = {"key": "value"}
    path = tmp_path / "test.json"

    await write_json(path, data)

    content = path.read_text()
    assert "\n" in content  # Should have newlines from indent
    assert "  " in content  # Should have indentation
