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

# ── fix:queue ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_queue_no_project():
    ctx = _make_ctx(has_project=False)
    registry = CommandRegistry(MagicMock(), orchestrator=AsyncMock())
    await registry.execute("fix:queue", ctx)
    assert ctx.has_error
    assert any("No active project" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_queue_clean_project():
    ctx = _make_ctx()
    ctx.orchestrator.get_fix_queue.return_value = {"queue": [], "total": 0}
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("fix:queue", ctx)
    assert not ctx.has_error
    assert any("clean" in line for line in ctx.stdout_buffer)

@pytest.mark.asyncio
async def test_queue_renders_ranked_list():
    ctx = _make_ctx()
    ctx.orchestrator.get_fix_queue.return_value = {
        "total": 12,
        "queue": [
            {"rank": 1, "finding_hash": "a8f9c2b4d6e1", "rule_id": "SQL_INJECTION",
             "severity": "CRITICAL", "file_path": "src/auth/login.py",
             "age_days": 7, "score_impact": 14.1},
        ]
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("fix:queue --severity CRITICAL --limit 1", ctx)
    assert not ctx.has_error
    assert any("SQL_INJECTION" in line for line in ctx.stdout_buffer)
