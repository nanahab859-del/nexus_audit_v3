import pytest
import asyncio
from pathlib import Path
import yaml
from core.models import Settings
from core.config_loader import load_full_config, _deep_merge

def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99, "e": 4}, "f": 5}
    
    result = _deep_merge(base, override)
    
    assert result["a"] == 1
    assert result["b"]["c"] == 99
    assert result["b"]["d"] == 3
    assert result["b"]["e"] == 4
    assert result["f"] == 5

@pytest.mark.asyncio
async def test_load_full_config(tmp_path):
    # We will just test that it works without crashing
    config = await load_full_config(tmp_path / "settings.json")
    assert isinstance(config, dict)
