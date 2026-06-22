import pytest
from unittest.mock import AsyncMock, MagicMock
from core.primitives.commands.context import CommandContext, OPERATOR, READONLY
from core.primitives.commands.registry import CommandRegistry

def _make_ctx(privilege=OPERATOR, has_project=True):
    ctx = MagicMock(spec=CommandContext)
    ctx.stdout_buffer = []
    ctx.has_error = False
    ctx.active_project = MagicMock(id="proj-001") if has_project else None
    ctx.privilege_level = privilege
    ctx.orchestrator = AsyncMock()
    ctx.write = lambda t: ctx.stdout_buffer.append(t)
    ctx.write_error = lambda t: ctx.stdout_buffer.append(f"[ERROR] {t}") or setattr(ctx, "has_error", True)
    return ctx

# ── audit:diff ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diff_no_project():
    ctx = _make_ctx(has_project=False)
    registry = CommandRegistry(MagicMock(), orchestrator=AsyncMock())
    await registry.execute("audit:diff", ctx)
    assert ctx.has_error
    assert any("No active project" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_diff_renders_delta():
    ctx = _make_ctx()
    ctx.orchestrator.diff_runs.return_value = {
        "run_id_a": "2026-06-08T10-00Z_abc",
        "run_id_b": "2026-06-15T14-00Z_def",
        "score_delta": {"overall": -9.2, "security": -14.1, "quality": 4.9},
        "new_findings": {"count": 3, "by_severity": {"CRITICAL": 1, "HIGH": 2}},
        "resolved_findings": {"count": 1},
        "coupling_changes": {"added_edges": [["auth", "payments"]], "removed_edges": []},
        "probable_commit": "a3f9c2b",
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:diff", ctx)
    assert not ctx.has_error
    assert any("−9.2" in line or "-9.2" in line for line in ctx.stdout_buffer)
    assert any("auth" in line for line in ctx.stdout_buffer)

# ── audit:trend ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trend_no_runs():
    ctx = _make_ctx()
    ctx.orchestrator.get_trend.return_value = {"runs": []}
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:trend", ctx)
    assert not ctx.has_error
    assert any("No audit runs" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_trend_renders_table():
    ctx = _make_ctx()
    ctx.orchestrator.get_trend.return_value = {
        "runs": [
            {"timestamp": "2026-06-14T10:00:00Z", "git_commit": "abc1234",
             "scores": {"overall": 88.0, "security": 84.0, "quality": 90.0},
             "counts": {"critical": 0, "high": 2}},
            {"timestamp": "2026-06-15T14:00:00Z", "git_commit": "def5678",
             "scores": {"overall": 82.4, "security": 78.1, "quality": 88.0},
             "counts": {"critical": 1, "high": 5}},
        ]
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:trend --last 2", ctx)
    assert not ctx.has_error
    assert any("88.0" in line for line in ctx.stdout_buffer)
    assert any("▼" in line for line in ctx.stdout_buffer)   # regression arrow

# ── audit:export ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_no_project():
    ctx = _make_ctx(has_project=False)
    registry = CommandRegistry(MagicMock(), orchestrator=AsyncMock())
    await registry.execute("audit:export", ctx)
    assert ctx.has_error
    assert any("No active project" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_export_success():
    ctx = _make_ctx()
    ctx.orchestrator.export_audit.return_value = {
        "findings_count": 42,
        "output_path": "/tmp/export.sarif"
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:export --format sarif", ctx)
    assert not ctx.has_error
    assert any("42" in line for line in ctx.stdout_buffer)
    assert any("/tmp/export.sarif" in line for line in ctx.stdout_buffer)
