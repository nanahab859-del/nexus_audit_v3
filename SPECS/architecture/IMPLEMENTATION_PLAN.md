# Implementation Plan — MCP Server + SQLite Audit Index

**Branch:** `feature/mcp-server-sqlite-index`
**Status:** Plan only. Nothing in this list has been written yet.
See `SUMMARY.md` in this same branch for the why; this file is the how.

Two phases, in order. Phase 1 is small, self-contained, and has nothing to
do with Phase 2 — it's done first because it's the faster path to a clean
checkpoint before the larger MCP build starts.

---

## Phase 1 — SQLite Index

### New file: `core/infra/audit_index.py`

- `_PRAGMAS` — the three WAL pragmas (`journal_mode=WAL`,
  `synchronous=NORMAL`, `busy_timeout=5000`)
- `_SCHEMA_SQL` — `runs` table, `findings` table, indexes — matching the
  schema already documented in the storage spec
- `async def open_index(project_id: str)` — resolves
  `~/.nexus_audit/projects/<project_id>/nexus_state.db`, applies pragmas,
  creates the schema if missing, returns a connection
- `async def upsert_run(project_id: str, summary: dict, job_dir: Path)` —
  one row into `runs` (job_id, timestamp, fleet_average, app_scores as
  JSON text, findings_count, git_commit, git_branch), one row per
  fingerprint into `findings` (fingerprint, run_id, rule_id)
- `async def rebuild_index(project_id: str) -> dict` — deletes and
  recreates `nexus_state.db`, replays every `audit_summary.json` under
  `~/.nexus_audit/projects/<id>/jobs/`, returns `{"runs_indexed": N}`

### Modified file: `orchestrator.py` — one line, one place

Inside `_run_job()`, in the existing "write output" phase, immediately
after the line that writes `audit_summary.json`:

```python
await write_json(output_dir / "audit_summary.json", self._build_summary(result_data), indent=2)
await upsert_run(project_id, self._build_summary(result_data), output_dir)   # ← new line
```

Nothing else in this file changes in this phase. No new Orchestrator
methods. `get_trend` / `diff_runs` / `get_fix_queue` / `export_audit` are
not touched, not added, not stubbed — that surface belongs to the other
branch.

### New file: `core/primitives/commands/handlers/index_ext.py`

- `audit:rebuild-index` command — OPERATOR privilege (proposed; same
  tier as the read-mostly, easily-rerunnable commands already in this
  codebase — flagging in case a stricter tier is preferred)
- Calls `rebuild_index()`, writes `"Index rebuilt: N run(s) indexed."`

### Modified file: `core/primitives/commands/registry.py` — two lines

`index_ext` added to the `_register_all()` import tuple, plus one
`index_ext.register(self)` call. Nothing else in this file changes.

### Tests

- `tests/infra/test_audit_index.py`
  - schema creates both tables on first open
  - WAL pragma is actually active after open (`PRAGMA journal_mode`
    returns `'wal'`)
  - `upsert_run` inserts a row with the right columns
  - `upsert_run` called twice with the same job_id does not duplicate
    (`INSERT OR REPLACE`)
  - `rebuild_index` against 3 fake job dirs produces 3 rows in `runs`
  - `rebuild_index` run twice in a row produces the same row count
    (idempotent, matches the spec's "always rebuildable" guarantee)
  - `findings` table contains one row per fingerprint per run

- `tests/primitives/test_index_ext.py`
  - `audit:rebuild-index` with no active project → error
  - renders the run count on success
  - alias / privilege check, matching the existing handler test pattern

### Checkpoint

Run the new test files in isolation, then re-run
`tests/orchestrator/ tests/primitives/ tests/engines/test_fix_queue.py`
to confirm the one-line orchestrator hook didn't break anything that was
passing before. One commit, on this branch only.

---

## Phase 2 — MCP Server (not started)

### Dependency change: `pyproject.toml`

Adds `fastmcp>=3.0,<4`, `mcp>=1.25,<2`, `pydantic>=2.5`, `aiosqlite>=0.20`.
None of these are currently a dependency of this project — flagging
explicitly before anything gets installed into the venv.

### New package: `core/mcp/`

- `server.py` — STDIO transport entrypoint. All logging forced to
  `stderr` (Section 8.1 of the MCP spec — a single stray `print()`
  anywhere in this package corrupts the JSON-RPC stream and crashes the
  connection)
- `security.py` — `_assert_safe_path()`, sandboxing every path argument
  to `~/.nexus_audit/`
- `tools/info.py` — `get_server_info`
- `tools/audit.py` — `run_project_audit` (wraps the existing
  `orchestrator.start_job`), `get_latest_audit_summary` (reads the
  latest `audit_summary.json` directly)
- `tools/findings.py` — `get_finding_detail`, `list_findings`,
  `get_file_context` — all direct reads of `audit_data_complete.json`,
  paginated and capped server-side per the spec (max 100 per call)

### Explicitly deferred in this phase

`get_fix_queue`, `get_trend`, `diff_runs` as MCP tools. Their Pydantic
input schemas get defined (so the contract is documented and stable),
but the tool bodies are not wired — they depend on Orchestrator methods
that exist on the other branch, not this one. Wiring them later is
mechanical: call the method, shape the response, done.

### New file: `core/primitives/commands/handlers/mcp.py`

- `mcp:config` — ADMIN privilege, writes the agent host config entry
  (Claude Desktop / Cursor), does not spawn any process
- `mcp:status` — READONLY, reports whether the entry is present

### Tests

- STDIO purity test — start the server, send `initialize`, assert every
  line on stdout is valid JSON-RPC (Section 11.3 of the spec)
- Path sandbox tests — confirm `~/.ssh/id_rsa` and `../../etc/passwd`
  style paths are rejected
- Pydantic validation tests for each tool's input model
- Integration test simulating one discovery → audit → list → detail
  cycle through the MCP test client

### Checkpoint

Run the full new test set, manual smoke test with
`npx @modelcontextprotocol/inspector python -m core.mcp.server`, confirm
the tool list registers with no stderr errors. One commit, on this
branch only.

---

## What never happens on this branch, in either phase

- `main` is not checked out, merged into, or modified
- `get_trend`, `diff_runs`, `get_fix_queue` Orchestrator methods are not
  implemented here
- No other branch is deleted, merged from, or rebased onto
