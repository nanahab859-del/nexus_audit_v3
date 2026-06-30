# Fix: `test_pydantic_validation` is a false-positive test

**Found:** 2026-06-30, during full-suite verification run
**File:** `tests/mcp/test_mcp_server.py`
**Severity:** Medium — not a production bug, but the test provides zero real
coverage for MCP tool registration and currently passes regardless of input.

## Root cause

`core/mcp/server.py` exposes `mcp` as a `FastMCP` instance. `FastMCP.get_tool`
is `async def get_tool(self, name: str, version: VersionSpec | None = None) ->
Tool | None` (confirmed via `inspect.iscoroutinefunction`, 2026-06-30).

The test calls it synchronously:

```python
def test_pydantic_validation():
    """Verify pydantic models validate input types."""
    from core.mcp.server import mcp

    assert mcp.get_tool("run_project_audit") is not None
    assert mcp.get_tool("get_latest_audit_summary") is not None
    assert mcp.get_tool("list_findings") is not None
    assert mcp.get_tool("get_finding_detail") is not None
    assert mcp.get_tool("get_file_context") is not None
```

Because `get_tool` is never awaited, each call returns a **coroutine object**,
not a `Tool | None`. A coroutine object is always truthy and never `None`, so
every `assert ... is not None` passes unconditionally — even if every tool
name above were misspelled or none of the tools existed. Confirmed by the
`RuntimeWarning: coroutine 'FastMCP.get_tool' was never awaited` emitted on
every test run (5 instances, one per assertion).

## Exact fix

```python
async def test_pydantic_validation():
    """Verify the five MCP tools are registered and resolvable by name."""
    from core.mcp.server import mcp

    assert await mcp.get_tool("run_project_audit") is not None
    assert await mcp.get_tool("get_latest_audit_summary") is not None
    assert await mcp.get_tool("list_findings") is not None
    assert await mcp.get_tool("get_finding_detail") is not None
    assert await mcp.get_tool("get_file_context") is not None
```

Two changes: `def` → `async def` (pytest-asyncio is already configured in
`pytest.ini`, `mode=strict`, so the project's existing async test convention
applies — check whether other async tests in this file/dir use a
`@pytest.mark.asyncio` decorator or rely on `asyncio_mode = auto`; match
whatever the rest of `tests/mcp/` already does), and `await` added to each of
the five calls.

## Verification checklist (for me to confirm after the agent implements)

- [ ] `def test_pydantic_validation()` is now `async def`, consistent with the asyncio mode already configured for this test file/dir
- [ ] All 5 `mcp.get_tool(...)` calls are awaited
- [ ] `.venv/bin/pytest tests/mcp -q` passes with **zero** `RuntimeWarning` about unawaited coroutines
- [ ] Sanity check the test actually catches a broken tool name: temporarily rename one assertion's tool string to something nonexistent (e.g. `"run_project_audit_typo"`), confirm the test now **fails**, then revert — this proves the assertion is meaningful post-fix (not part of the committed diff, just a manual check)
- [ ] No other test in the repo calls `mcp.get_tool(...)` synchronously (grep `\.get_tool(` across `tests/`)

## Not in scope for this fix

The `MockProc.communicate` "never awaited" warnings in
`tests/infra/test_fast_check.py::test_run_git_command_terminate_exception` and
`tests/infra/test_git_context.py::test_get_git_context_timeout` are a
**separate, lower-priority** issue — traced to those tests' own
`mock_wait_for` stub discarding the coroutine passed into it instead of
awaiting or closing it. `core/infra/git_utils.py:run_git()` itself is correct;
real `asyncio.wait_for` always awaits-or-cancels its argument. Do not bundle
a fix for this into the same PR — separate concern, separate plan if/when prioritised.
