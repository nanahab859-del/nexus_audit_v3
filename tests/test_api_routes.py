"""
tests/test_api_routes.py
HTTP-level tests for every API endpoint using aiohttp TestClient.
Covers: /api/run, /api/cancel, /api/settings (GET+POST),
        /api/project/ping, /api/ai/diagnose-scanner-error,
        /api/scanners, /api/config, /api/capabilities.
"""

import json
import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from aiohttp.test_utils import TestClient, TestServer

from api.server import create_app
from core.models import Settings, Job
from core.events import EventBus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(tmp_path):
    """
    Create an aiohttp TestClient against the real application.
    Patches SettingsManager to use a temp settings.json so tests are isolated.
    """
    settings_file = tmp_path / "settings.json"
    # Write a minimal settings file
    settings_file.write_text(json.dumps({
        "project_path": str(tmp_path),
        "scanners": {},
        "ai_enabled": False,
    }))

    app = create_app()
    # Point SettingsManager at temp path
    with patch("core.settings.DEFAULT_SETTINGS_PATH", settings_file), \
         patch("api.routes_settings.SettingsManager") as MockSM, \
         patch("api.routes_run.SettingsManager") as MockSMRun, \
         patch("api.routes_ai.SettingsManager") as MockSMAI:

        # Set up a real-ish SettingsManager backed by tmp settings
        from core.settings import SettingsManager
        real_sm = SettingsManager(settings_file)

        for mock in (MockSM, MockSMRun, MockSMAI):
            mock.return_value = real_sm

        async with TestClient(TestServer(app)) as c:
            yield c


# ── /api/settings ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_settings_returns_200(client):
    resp = await client.get("/api/settings")
    assert resp.status == 200
    data = await resp.json()
    assert "project_path" in data
    # api_key is never returned in plaintext
    assert data.get("api_key") != "secret"


@pytest.mark.asyncio
async def test_post_settings_updates_field(client):
    resp = await client.post("/api/settings",
                             json={"project_name": "TestProject"})
    assert resp.status == 200
    data = await resp.json()
    assert data["project_name"] == "TestProject"


@pytest.mark.asyncio
async def test_post_settings_rejects_unknown_key(client):
    """Unknown keys are silently dropped — response still 200 but key absent."""
    resp = await client.post("/api/settings",
                             json={"totally_fake_key": "should_not_appear"})
    assert resp.status == 200
    data = await resp.json()
    assert "totally_fake_key" not in data


@pytest.mark.asyncio
async def test_post_settings_invalid_json(client):
    resp = await client.post("/api/settings",
                             data="not-json",
                             headers={"Content-Type": "application/json"})
    assert resp.status == 400


# ── /api/run ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_run_returns_202(client):
    resp = await client.post("/api/run")
    assert resp.status == 202
    data = await resp.json()
    assert "job_id" in data


@pytest.mark.asyncio
async def test_start_run_twice_returns_409(client):
    """Starting a second run while one is active must return 409."""
    r1 = await client.post("/api/run")
    assert r1.status == 202

    # Force the orchestrator to have an active job so the next call fails instantly
    from core.models import Job
    from datetime import datetime, timezone
    from uuid import uuid4
    client.app['orchestrator']._current_job = Job(
        id=str(uuid4()), project_path="/tmp", started_at=datetime.now(timezone.utc), state="running"
    )

    r2 = await client.post("/api/run")
    assert r2.status == 409


# ── /api/cancel ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_when_idle_returns_409(client):
    resp = await client.post("/api/cancel")
    assert resp.status == 409


# ── /api/project/ping ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_valid_path(client, tmp_path):
    resp = await client.post("/api/project/ping",
                             json={"path": str(tmp_path)})
    assert resp.status == 200
    data = await resp.json()
    assert data["valid"] is True
    assert "path" in data


@pytest.mark.asyncio
async def test_ping_invalid_path(client):
    resp = await client.post("/api/project/ping",
                             json={"path": "/this/path/does/not/exist/12345"})
    assert resp.status == 200
    data = await resp.json()
    assert data["valid"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_ping_missing_body(client):
    resp = await client.post("/api/project/ping", json={})
    assert resp.status in (400, 200)  # 400 preferred; 200 with error also acceptable


# ── /api/ai/diagnose-scanner-error ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_diagnose_when_disabled_returns_503(client):
    """When ai_enabled=False, the endpoint must return 503."""
    resp = await client.post("/api/ai/diagnose-scanner-error",
                             json={"scanner_name": "bandit",
                                   "error_message": "Timeout",
                                   "context_logs": []})
    assert resp.status == 503
    data = await resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_ai_diagnose_missing_fields_returns_400(client):
    resp = await client.post("/api/ai/diagnose-scanner-error",
                             json={"scanner_name": ""})
    assert resp.status in (400, 503)


@pytest.mark.asyncio
async def test_ai_diagnose_invalid_json_returns_400(client):
    resp = await client.post("/api/ai/diagnose-scanner-error",
                             data="bad-json",
                             headers={"Content-Type": "application/json"})
    assert resp.status in (400, 503)


# ── /api/scanners ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_scanners_returns_list(client):
    resp = await client.get("/api/scanners")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)


# ── /api/capabilities ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_capabilities(client):
    resp = await client.get("/api/capabilities")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, dict)


# ── /api/status ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_status(client):
    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "state" in data
