import asyncio
import time
import pytest
from core.infra.key_pool import KeyPool

@pytest.mark.asyncio
async def test_init_with_keys():
    pool = KeyPool("key1", ["key2", "key3"])
    assert pool.total_count == 3

@pytest.mark.asyncio
async def test_next_key_returns_available():
    pool = KeyPool("key1")
    key = await pool.next_key()
    assert key == "key1"

@pytest.mark.asyncio
async def test_exhausted_key_skipped():
    pool = KeyPool("key1", ["key2"], cooldown_seconds=1)
    k1 = await pool.next_key()
    assert k1 == "key1"
    
    await pool.mark_rate_limited("key1")
    
    k2 = await pool.next_key()
    assert k2 == "key2"

@pytest.mark.asyncio
async def test_cooldown_expiry():
    pool = KeyPool("key1", cooldown_seconds=1)
    await pool.next_key()
    await pool.mark_rate_limited("key1")
    
    # Key should be exhausted
    assert await pool.next_key() is None
    
    # Wait for cooldown
    await asyncio.sleep(1.1)
    
    # Should be back
    assert await pool.next_key() == "key1"

@pytest.mark.asyncio
async def test_all_exhausted_returns_none():
    pool = KeyPool("key1", cooldown_seconds=1)
    await pool.next_key()
    await pool.mark_rate_limited("key1")
    
    assert await pool.next_key() is None

@pytest.mark.asyncio
async def test_remove_key_permanent():
    pool = KeyPool("key1", ["key2"])
    await pool.remove_key("key1")
    
    assert pool.total_count == 1
    assert await pool.next_key() == "key2"
    
    # key1 should not return
    for _ in range(5):
        assert await pool.next_key() != "key1"

@pytest.mark.asyncio
async def test_async_safety():
    pool = KeyPool("key1", ["key2", "key3"])
    
    async def task():
        k = await pool.next_key()
        if k:
            await asyncio.sleep(0.01)
    
    await asyncio.gather(*(task() for _ in range(10)))
    # Verification of state integrity is difficult here, 
    # but the test checks for crashes/deadlocks
    pass

@pytest.mark.asyncio
async def test_add_key_success():
    pool = KeyPool("key1")
    await pool.add_key("key2")
    assert pool.total_count == 2
    assert await pool.available_count() == 2

@pytest.mark.asyncio
async def test_available_count():
    pool = KeyPool("key1", ["key2"], cooldown_seconds=1)
    assert await pool.available_count() == 2
    await pool.mark_rate_limited("key1")
    assert await pool.available_count() == 1
    await pool.mark_rate_limited("key2")
    assert await pool.available_count() == 0
    # Wait for cooldown
    await asyncio.sleep(1.1)
    assert await pool.available_count() == 2
