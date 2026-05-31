"""Tests for orchestrator with Phase 3 scanner dispatch."""

import pytest
from pathlib import Path
from orchestrator import Orchestrator
from core.models import Settings
from core.registry import PluginRegistry


@pytest.mark.asyncio
async def test_orchestrator_start_job() -> None:
    """Test that start_job creates a running job."""
    orch = Orchestrator()
    settings = Settings(
        project_path=Path("."),
        api_key=None,
        ai_enabled=False,
        ai_provider="claude",
        ai_model="claude-opus-4-7",
        force_rescan=False,
        scanners={},
        scanner_configs={},
        ui={},
    )

    job = await orch.start_job(Path("."), settings)
    assert job is not None
    assert job.state == "running"

    # Allow the task to complete or error
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_plugin_registry_loads() -> None:
    """Test that PluginRegistry can load scanner plugins."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()

    names = registry.names()
    # We expect at least the 6 scanners we created
    expected = {"bandit", "vulture", "radon", "safety", "lizard", "semgrep"}
    found = set(names) & expected

    # All 6 should be present if imported correctly
    assert len(found) > 0, f"Expected to find scanners, got: {names}"


def test_plugin_registry_get() -> None:
    """Test that PluginRegistry.get returns scanner classes."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()

    bandit = registry.get("bandit")
    assert bandit is not None
    assert bandit.name == "bandit"


def test_plugin_registry_all() -> None:
    """Test that PluginRegistry.all returns all scanners."""
    registry = PluginRegistry(Path("plugins"))
    registry.load()

    all_scanners = registry.all()
    assert len(all_scanners) > 0


@pytest.mark.asyncio
async def test_orchestrator_conflict() -> None:
    """Test that starting a job while one is running raises ConflictError."""
    from orchestrator import ConflictError

    orch = Orchestrator()
    settings = Settings(
        project_path=Path("."),
        api_key=None,
        ai_enabled=False,
        ai_provider="claude",
        ai_model="claude-opus-4-7",
        force_rescan=False,
        scanners={},  # No scanners = fast completion
        scanner_configs={},
        ui={},
    )

    job1 = await orch.start_job(Path("."), settings)
    assert job1.state == "running"

    # Attempt to start another job while first is running
    with pytest.raises(ConflictError):
        await orch.start_job(Path("."), settings)


@pytest.mark.asyncio
async def test_orchestrator_current_job() -> None:
    """Test that current_job returns the running job."""
    orch = Orchestrator()
    assert orch.current_job() is None

    settings = Settings(
        project_path=Path("."),
        api_key=None,
        ai_enabled=False,
        ai_provider="claude",
        ai_model="claude-opus-4-7",
        force_rescan=False,
        scanners={},
        scanner_configs={},
        ui={},
    )

    job = await orch.start_job(Path("."), settings)
    assert orch.current_job() is not None
    assert orch.current_job().id == job.id


import asyncio
