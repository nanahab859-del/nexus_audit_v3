"""Tests for api.routes_data endpoints."""

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web
from pathlib import Path
import json

from api.server import create_app
from orchestrator import Orchestrator


class TestApiData(AioHTTPTestCase):
    """Test data endpoints."""

    async def get_application(self) -> web.Application:
        """Create test app."""
        return create_app(Orchestrator())

    @unittest_run_loop
    async def test_status_idle(self) -> None:
        """Test GET /api/status returns idle when no job."""
        async with self.client.get("/api/status") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["state"] == "idle"
            assert data["job_id"] is None

    @unittest_run_loop
    async def test_data_no_audit(self) -> None:
        """Test GET /api/data when no audit has run."""
        async with self.client.get("/api/data") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["findings"] == []
            assert data["job"] is None

    @unittest_run_loop
    async def test_history_empty(self) -> None:
        """Test GET /api/history returns empty list initially."""
        async with self.client.get("/api/history") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data == []

    @unittest_run_loop
    async def test_history_item_not_found(self) -> None:
        """Test GET /api/history/nonexistent returns 404."""
        async with self.client.get("/api/history/nonexistent") as resp:
            assert resp.status == 404
            data = await resp.json()
            assert "error" in data
