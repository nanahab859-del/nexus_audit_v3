"""
tests/test_routes_ai.py
Unit tests for the AI diagnostics route stub (without an HTTP client).
Tests the handler function directly by mocking aiohttp Request.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web

from api.routes_ai import diagnose_scanner_error, STUB_ADVICE, GENERIC_ADVICE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(body: dict | str, ai_enabled: bool = False):
    """Build a minimal mock aiohttp Request."""
    req = MagicMock(spec=web.Request)
    if isinstance(body, dict):
        raw = json.dumps(body).encode()
        req.json = AsyncMock(return_value=body)
    else:
        raw = body.encode() if isinstance(body, str) else body
        req.json = AsyncMock(side_effect=Exception("bad json"))

    from core.models import Settings
    settings = Settings(ai_enabled=ai_enabled)

    return req, settings


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diagnose_returns_503_when_ai_disabled():
    req, settings = _make_request(
        {"scanner_name": "bandit", "error_message": "Timeout"}, ai_enabled=False
    )
    with patch("api.routes_ai.SettingsManager") as MockSM:
        sm_instance = AsyncMock()
        sm_instance.load = AsyncMock(return_value=settings)
        MockSM.return_value = sm_instance

        resp = await diagnose_scanner_error(req)

    assert resp.status == 503
    body = json.loads(resp.body)
    assert "error" in body


@pytest.mark.asyncio
async def test_diagnose_returns_analysis_when_ai_enabled():
    req, settings = _make_request(
        {"scanner_name": "vulture", "error_message": "timeout", "context_logs": []},
        ai_enabled=True
    )
    settings.ai_enabled = True

    with patch("api.routes_ai.SettingsManager") as MockSM:
        sm_instance = AsyncMock()
        sm_instance.load = AsyncMock(return_value=settings)
        MockSM.return_value = sm_instance

        resp = await diagnose_scanner_error(req)

    assert resp.status == 200
    body = json.loads(resp.body)
    assert "analysis" in body
    assert len(body["analysis"]) > 0


@pytest.mark.asyncio
async def test_diagnose_known_scanner_returns_canned_advice():
    """Known scanner names (bandit, vulture, safety) return scanner-specific advice."""
    from core.models import Settings
    settings = Settings(ai_enabled=True)

    for scanner_name in STUB_ADVICE.keys():
        req = MagicMock(spec=web.Request)
        req.json = AsyncMock(return_value={
            "scanner_name": scanner_name,
            "error_message": "some error",
        })
        with patch("api.routes_ai.SettingsManager") as MockSM:
            sm_instance = AsyncMock()
            sm_instance.load = AsyncMock(return_value=settings)
            MockSM.return_value = sm_instance
            resp = await diagnose_scanner_error(req)

        body = json.loads(resp.body)
        assert body["analysis"] == STUB_ADVICE[scanner_name], \
            f"Expected canned advice for {scanner_name}"


@pytest.mark.asyncio
async def test_diagnose_unknown_scanner_returns_generic_advice():
    from core.models import Settings
    settings = Settings(ai_enabled=True)

    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(return_value={
        "scanner_name": "unknown_scanner_xyz",
        "error_message": "crash",
    })
    with patch("api.routes_ai.SettingsManager") as MockSM:
        sm_instance = AsyncMock()
        sm_instance.load = AsyncMock(return_value=settings)
        MockSM.return_value = sm_instance
        resp = await diagnose_scanner_error(req)

    body = json.loads(resp.body)
    assert body["analysis"] == GENERIC_ADVICE


@pytest.mark.asyncio
async def test_diagnose_missing_fields_returns_400():
    from core.models import Settings
    settings = Settings(ai_enabled=True)

    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(return_value={"scanner_name": ""})  # empty scanner_name

    with patch("api.routes_ai.SettingsManager") as MockSM:
        sm_instance = AsyncMock()
        sm_instance.load = AsyncMock(return_value=settings)
        MockSM.return_value = sm_instance
        resp = await diagnose_scanner_error(req)

    assert resp.status == 400


@pytest.mark.asyncio
async def test_diagnose_invalid_json_returns_400():
    from core.models import Settings
    settings = Settings(ai_enabled=True)

    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(side_effect=Exception("parse error"))

    with patch("api.routes_ai.SettingsManager") as MockSM:
        sm_instance = AsyncMock()
        sm_instance.load = AsyncMock(return_value=settings)
        MockSM.return_value = sm_instance
        resp = await diagnose_scanner_error(req)

    assert resp.status == 400
