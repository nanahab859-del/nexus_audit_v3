"""Tests for api.routes_run endpoints."""

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web
from pathlib import Path

from api.server import create_app
from orchestrator import Orchestrator, ConflictError
from core.settings import save as save_settings
from core.models import Settings


class TestApiRun(AioHTTPTestCase):
    """Test job control endpoints."""

    async def get_application(self) -> web.Application:
        """Create test app."""
        orc = Orchestrator()
        app = create_app(orc, settings_path=Path(".settings.json"))

        # Create valid settings
        settings = Settings(project_path=Path("."))
        await save_settings(settings, Path(".settings.json"))

        return app

    def tearDown(self) -> None:
        """Clean up after tests."""
        Path(".settings.json").unlink(missing_ok=True)
        super().tearDown()


    @unittest_run_loop
    async def test_post_run_success(self) -> None:
        """Test POST /api/run starts a job."""
        async with self.client.post("/api/run") as resp:
            assert resp.status == 202
            data = await resp.json()
            assert "job_id" in data
            assert len(data["job_id"]) > 0

    @unittest_run_loop
    async def test_post_run_conflict(self) -> None:
        """Test POST /api/run returns 409 if job already running."""
        # Start first job
        async with self.client.post("/api/run") as resp:
            assert resp.status == 202

        # Try to start second job
        async with self.client.post("/api/run") as resp:
            assert resp.status == 409
            data = await resp.json()
            assert "error" in data

    @unittest_run_loop
    async def test_post_cancel_success(self) -> None:
        """Test POST /api/cancel cancels job."""
        # Start a job
        async with self.client.post("/api/run") as resp:
            assert resp.status == 202

        # Cancel it
        async with self.client.post("/api/cancel") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True

    @unittest_run_loop
    async def test_post_cancel_no_job(self) -> None:
        """Test POST /api/cancel returns 200 even if no job running."""
        async with self.client.post("/api/cancel") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True
