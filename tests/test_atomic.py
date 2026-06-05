import pytest
from pathlib import Path
from core.atomic import write_json, read_json

@pytest.mark.asyncio
async def test_atomic_write_read(tmp_path):
    path = tmp_path / "test.json"
    data = {"key": "value"}
    
    await write_json(path, data)
    assert path.exists()
    
    read_data = await read_json(path)
    assert read_data == data

@pytest.mark.asyncio
async def test_read_nonexistent():
    path = Path("nonexistent.json")
    data = await read_json(path)
    assert data is None
