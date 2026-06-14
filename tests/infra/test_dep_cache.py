import asyncio
import time
import pytest
import json
from pathlib import Path
from core.infra.dep_cache import DepCache

@pytest.mark.asyncio
async def test_cache_miss(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    assert await cache.get("flask", "1.0") is None

@pytest.mark.asyncio
async def test_cache_hit(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    data = {"vulns": []}
    await cache.set("flask", "1.0", data)
    await cache.save()
    
    # Retrieve
    result = await cache.get("flask", "1.0")
    assert result == data

@pytest.mark.asyncio
async def test_cache_expired(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    data = {"vulns": []}
    
    # Manually set expired data
    await cache.set("flask", "1.0", data)
    # Hack: access private _data to expire
    key = cache._cache_key("flask", "1.0")
    cache._data[key]["cached_at"] = time.time() - (DepCache.DEFAULT_TTL + 10)
    
    assert await cache.get("flask", "1.0") is None

@pytest.mark.asyncio
async def test_force_rescan(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    await cache.set("flask", "1.0", {"data": 1})
    
    assert await cache.get("flask", "1.0", force_rescan=True) is None

@pytest.mark.asyncio
async def test_key_normalization(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    await cache.set("Flask-JWT-Extended", "1.0", {"data": 1})
    
    assert await cache.get("flask_jwt_extended", "1.0") == {"data": 1}

@pytest.mark.asyncio
async def test_persistence(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache1 = DepCache(cache_path=cache_path)
    data = {"vulns": ["CVE-1"]}
    await cache1.set("pkg", "2.0", data)
    await cache1.save()
    
    # New instance
    cache2 = DepCache(cache_path=cache_path)
    assert await cache2.get("pkg", "2.0") == data

@pytest.mark.asyncio
async def test_corrupt_file(tmp_path, caplog):
    cache_path = tmp_path / "dep_cache.json"
    with open(cache_path, "w") as f:
        f.write("not-json")
        
    cache = DepCache(cache_path=cache_path)
    result = await cache.get("pkg", "1.0")
    assert result is None
    assert "Corrupt cache file" in caplog.text or "Failed to load cache" in caplog.text

@pytest.mark.asyncio
async def test_clear(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    await cache.set("pkg", "1.0", {"a": 1})
    await cache.clear()
    
    assert await cache.get("pkg", "1.0") is None

@pytest.mark.asyncio
async def test_concurrent_access(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    
    async def setter(i):
        await cache.set(f"pkg{i}", "1.0", {"i": i})
        
    await asyncio.gather(*(setter(i) for i in range(10)))
    await cache.save()
    
    # Verify all were set
    for i in range(10):
        assert await cache.get(f"pkg{i}", "1.0") == {"i": i}

@pytest.mark.asyncio
async def test_load_internal_early_return(tmp_path):
    cache_path = tmp_path / "dep_cache.json"
    cache = DepCache(cache_path=cache_path)
    await cache._load_internal()
    assert cache._loaded is True
    # Calling it again should trigger early return
    await cache._load_internal()
    assert cache._loaded is True

@pytest.mark.asyncio
async def test_load_internal_list(tmp_path, caplog, monkeypatch):
    cache_path = tmp_path / "dep_cache.json"
    cache_path.write_text("[]") # write a list
    cache = DepCache(cache_path=cache_path)
    await cache.get("pkg", "1.0")
    assert "Corrupt cache file" in caplog.text

@pytest.mark.asyncio
async def test_load_internal_exception(tmp_path, caplog, monkeypatch):
    cache_path = tmp_path / "dep_cache.json"
    cache_path.write_text("{}")
    
    # Mock read_json to raise
    async def mock_read_json(*args, **kwargs):
        raise ValueError("Simulated read failure")
        
    monkeypatch.setattr("core.infra.dep_cache.read_json", mock_read_json)
    
    cache = DepCache(cache_path=cache_path)
    await cache.get("pkg", "1.0")
    assert "Failed to load cache" in caplog.text
