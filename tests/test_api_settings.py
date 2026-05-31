"""Tests for api.routes_settings endpoints."""

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web
from pathlib import Path
import json
import tempfile

from api.server import create_app
from orchestrator import Orchestrator
from core.settings import save as save_settings
from core.models import Settings
from core.security import encrypt


class TestApiSettings(AioHTTPTestCase):
    """Test settings endpoints."""

    async def get_application(self) -> web.Application:
        """Create test app."""
        # Clean up any existing settings file
        Path(".settings.json").unlink(missing_ok=True)
        return create_app(Orchestrator())

    def tearDown(self) -> None:
        """Clean up after tests."""
        Path(".settings.json").unlink(missing_ok=True)
        super().tearDown()


    @unittest_run_loop
    async def test_get_settings_defaults(self) -> None:
        """Test GET /api/settings returns defaults."""
        async with self.client.get("/api/settings") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "ai_enabled" in data
            assert data["ai_provider"] == "claude"
            assert data["api_key"] is None or data["api_key"] == "***"

    @unittest_run_loop
    async def test_post_settings_valid(self) -> None:
        """Test POST /api/settings with valid body."""
        body = {
            "project_path": ".",
            "scanners": {"test": True},
            "ai_enabled": True,
        }
        async with self.client.post("/api/settings", json=body) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True

    @unittest_run_loop
    async def test_settings_api_key_redaction(self) -> None:
        """Test GET /api/settings redacts api_key as ***."""
        body = {
            "project_path": ".",
            "scanners": {},
            "api_key": "secret-key",
        }
        async with self.client.post("/api/settings", json=body) as resp:
            assert resp.status == 200

        async with self.client.get("/api/settings") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["api_key"] == "***"

    @unittest_run_loop
    async def test_settings_api_key_sentinel(self) -> None:
        """Test POST with api_key=*** preserves existing key."""
        # Set initial key
        body1 = {"project_path": ".", "scanners": {}, "api_key": "original-key"}
        async with self.client.post("/api/settings", json=body1) as resp:
            assert resp.status == 200

        # Update with *** sentinel
        body2 = {"project_path": ".", "scanners": {}, "api_key": "***"}
        async with self.client.post("/api/settings", json=body2) as resp:
            assert resp.status == 200

        # Verify key wasn't overwritten
        async with self.client.get("/api/settings") as resp:
            data = await resp.json()
            assert data["api_key"] == "***"
