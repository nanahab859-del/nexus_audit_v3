# Plan: MCP Data Quality Fixes (Group B)
**Priority:** P1/P2 — can run in parallel with Group A
**Written by:** Lead Code Auditor, 2026-06-30
**Agent scope:** `orchestrator.py`, `core/infra/audit_index.py`, `core/mcp/tools/audit.py`, `core/primitives/commands/handlers/project.py` (or wherever `project:register` lives), ghost-file rule in `core/engines/rules_engine.py`
**Do NOT touch:** `boundary_engine.py`, anything in the integration agent's worktree

**Dependency note:** Fix B5 (snippet storage) is worth implementing now as a column addition, but snippet data will only be populated once Group A (scanner binaries) is done. Implement the column and the population logic; accept that it shows null until scanners run.

---

## Fix B1: `duration_ms: 0` hardcoded in `run_project_audit` MCP tool

**File:** `core/mcp/tools/audit.py`
**Line:** ~37 — `"duration_ms": 0, # not easily available without diffing timestamps`
**Symptom:** Every audit run via MCP reports zero duration; impossible to detect hung or skipped scans

**Root cause:** Comment acknowledges the issue. Both `started_at` and `finished_at` are available in `audit_data_complete.json` under `metadata.started_at` and `metadata.finished_at` as ISO strings.

**Fix:** In the `run_project_audit` tool function, after `data = json.load(f)`, also load `audit_data_complete.json` from the same `job_dir` to read the timestamps:

```python
# Read duration from complete data
duration_ms = 0
complete_path = summary_path.parent / "audit_data_complete.json"
if complete_path.exists():
    try:
        with open(complete_path, "r") as cf:
            complete = json.load(cf)
        meta = complete.get("metadata", {})
        started = meta.get("started_at")
        finished = meta.get("finished_at")
        if started and finished:
            from datetime import datetime, timezone
            s = datetime.fromisoformat(started.replace("Z", "+00:00"))
            f_ = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            duration_ms = int((f_ - s).total_seconds() * 1000)
    except Exception:
        pass

return {
    "run_id": data.get("job_id"),
    "status": status["state"],
    "duration_ms": duration_ms,   # <-- was hardcoded 0
    ...
}
```

---

## Fix B2: 16 of 18 ghost-file findings are false positives

**File:** `core/engines/rules_engine.py` (or `plugins/rules_engine` — find the ghost-file rule implementation)
**Symptom:** `app.py`, `pyproject.toml`, `audit_rules.yaml`, `.eslintrc.json`, `templates/index.html`, `tests/test_auth.py` and others flagged as ghost files

**Root cause:** The ghost-file rule flags any Python/project file not reachable via the import graph. It doesn't distinguish between importable modules and:
- Project entry points (`app.py`, `wsgi.py`, `manage.py`, `cli.py`, `server.py`)
- Configuration files (`pyproject.toml`, `setup.cfg`, `*.yaml`, `*.json`, `*.cfg`, `*.ini`, `*.toml`)
- Template files (`*.html`, `*.jinja2`)
- Test files (`tests/**/*.py`, `test_*.py`, `*_test.py`)
- Tool metadata (`.eslintrc.json`, `.ruff.toml`)
- `__init__.py` files
- Dotfiles (`.secrets`, `.env.*`)

**Fix — add an exclusion list to the ghost-file rule:**

Find where the ghost-file rule decides whether a file is a ghost. Add a function to check exclusions before flagging:

```python
_GHOST_FILE_EXCLUDES = {
    # Entry points
    "app.py", "wsgi.py", "asgi.py", "manage.py", "cli.py", "server.py",
    "main.py", "run.py", "worker.py", "celery.py", "gunicorn.conf.py",
    # Config / metadata
    "pyproject.toml", "setup.py", "setup.cfg", "conftest.py",
    "pytest.ini", "tox.ini", ".flake8", "mypy.ini",
    # Nexus-specific
    "audit_rules.yaml", ".nexus_fix_queue.json", "DUMMY_PROJECT_PLAN.md",
}

_GHOST_FILE_EXCLUDE_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini",
    ".html", ".jinja2", ".j2", ".txt", ".md", ".rst",
    ".sh", ".bash", ".env",
}

_GHOST_FILE_EXCLUDE_PATTERNS = [
    # Test files
    lambda p: p.name.startswith("test_") or p.name.endswith("_test.py"),
    # Test directories
    lambda p: "tests" in p.parts or "test" in p.parts,
    # Dotfiles
    lambda p: p.name.startswith("."),
    # __init__.py
    lambda p: p.name == "__init__.py",
]

def _is_ghost_file_excluded(file_path: Path) -> bool:
    if file_path.name in _GHOST_FILE_EXCLUDES:
        return True
    if file_path.suffix in _GHOST_FILE_EXCLUDE_EXTENSIONS:
        return True
    for pattern in _GHOST_FILE_EXCLUDE_PATTERNS:
        if pattern(file_path):
            return True
    return False
```

Before flagging a file as a ghost, call `_is_ghost_file_excluded(Path(file_path))` and skip if it returns `True`.

**Note to agent:** Find the exact location of the ghost-file rule before implementing — it may be in `core/engines/rules_engine.py`, in a plugin under `plugins/`, or in a separate rule file. Read the file first before making changes.

**Verification:** After fix, a fresh audit run against NexusTestBed should produce at most 2 ghost-file findings: `billing/subscriptions.py` and `src/ghost.py` (the intentionally planted ones). `app.py`, `pyproject.toml`, `audit_rules.yaml`, `.eslintrc.json`, `templates/index.html`, `tests/test_auth.py`, `DUMMY_PROJECT_PLAN.md`, `.nexus_fix_queue.json` should all be excluded.

---

## Fix B3: Duplicate project registration — no uniqueness check

**File:** Find the `project:register` handler (likely `core/primitives/commands/handlers/project.py`)
**Symptom:** 7 duplicate `nexus_audit_v3_integration` entries pointing to the same path

**Root cause:** `SettingsManager.register_project()` (or the command handler) does not check for an existing project with the same (name, path) combination before inserting.

**Fix — add a pre-check in the register handler:**

```python
# Before calling sm.register_project():
existing = [
    p for p in sm.load_workspace().projects
    if p.settings.project_path == str(resolved_path) or p.name == name
]
if existing:
    ctx.write(f"[warn] A project with this path or name already exists: {existing[0].name} ({existing[0].id[:8]})")
    ctx.write("Use `project:list` to see all registered projects. Use `project:delete` to remove duplicates.")
    return
```

**Cleanup note:** The 7 existing duplicate `nexus_audit_v3_integration` entries should be cleaned up manually. This fix prevents future duplicates but does not retroactively remove existing ones. The auditor will do this cleanup separately, not the agent.

---

## Fix B4: Ambiguous `{"error":"No jobs found"}` error messages

**File:** `core/mcp/tools/audit.py` — `get_latest_audit_summary` tool (and any other MCP tool that returns this message)
**Symptom:** A caller cannot distinguish between "project path not registered", "project registered but never audited", or "jobs directory missing"

**Fix — replace the generic message with specific ones:**

```python
@mcp.tool()
async def get_latest_audit_summary(input: ProjectInput) -> dict:
    try:
        project_id = await resolve_project_id(input.project_path)
    except Exception:
        return {"error": f"Project not registered: {input.project_path}. Run project:register first."}

    try:
        jobs_dir = _assert_safe_path(
            str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs")
        )
    except Exception as e:
        return {"error": str(e)}

    if not jobs_dir.exists() or not any(jobs_dir.iterdir()):
        return {
            "error": "Project is registered but has no audit runs yet.",
            "hint": "Run audit:run or call run_project_audit to start a scan."
        }

    # ... rest of function unchanged
```

Apply the same pattern to any other tool that currently returns a bare `"No jobs found"`.

---

## Fix B5: `snippet: null` — no snippet column in SQLite, not populated

**Files:** `core/infra/audit_index.py` (schema + `upsert_run`), `core/mcp/tools/` (wherever `list_findings` and `get_finding_detail` are implemented)

**Dependency:** Snippet content requires scanner binaries to be running (Group A Fix 1). Implement the storage layer now; snippets will auto-populate once scanners run.

**Part A — add `snippet TEXT` column to `findings` table:**

In `_SCHEMA_SQL` in `audit_index.py`, add the column:
```sql
CREATE TABLE IF NOT EXISTS findings (
    fingerprint TEXT,
    run_id TEXT,
    category TEXT,
    severity TEXT,
    file_path TEXT,
    snippet TEXT,                    -- NEW
    first_seen_run TEXT,
    last_seen_run TEXT,
    status TEXT
);
```

Add migration guard (same pattern as Fix 4 in Group A plan):
```python
try:
    conn.execute("ALTER TABLE findings ADD COLUMN snippet TEXT")
except sqlite3.OperationalError:
    pass  # Column already exists
```

Add the migration guard after `_SCHEMA_SQL` is executed in both `open_index()` and `upsert_run()`.

**Part B — populate snippet in `upsert_run()`:**

`_build_summary()` (deliberately lightweight) will not carry snippets. Read them from `complete_data` instead. After loading `complete_data`, build a fingerprint→snippet lookup:

```python
fp_to_snippet = {}
if complete_data:
    for f in complete_data.get("findings", []):
        fp = f.get("fingerprint")
        snip = f.get("snippet")
        if fp and snip:
            fp_to_snippet[fp] = snip[:500]  # cap at 500 chars to keep DB small
```

Then in the INSERT/UPDATE block:
```python
snippet = fp_to_snippet.get(fingerprint, "")
# In INSERT:
conn.execute('''
    INSERT INTO findings (fingerprint, run_id, category, severity, file_path,
                          snippet, first_seen_run, last_seen_run, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (..., snippet, ...))
# In UPDATE:
conn.execute('''
    UPDATE findings SET last_seen_run=?, status=?, run_id=?, severity=?,
                        category=?, file_path=?, snippet=?
    WHERE fingerprint=?
''', (..., snippet, fingerprint))
```

**Part C — surface `snippet` in MCP tool responses:**

Find `list_findings` and `get_finding_detail` tools (likely in `core/mcp/tools/`). Add `snippet` to their SELECT queries and include it in the returned dict. The field is already named `snippet` in the `Finding` dataclass — use the same name for consistency.

---

## Verification checklist (auditor runs after implementation)

- [ ] Fresh audit run: `duration_ms` in `run_project_audit` response is a positive integer (>1000ms for a real multi-scanner run)
- [ ] Fresh audit run: `list_findings` for NexusTestBed returns fewer than 5 ghost-file findings (FP reduction confirmed). The only expected ghost-file findings are `billing/subscriptions.py` and `src/ghost.py`
- [ ] `project:register` with a duplicate path returns a warning and does NOT create a second entry; `project:list` still shows only one entry for that path
- [ ] `get_latest_audit_summary` called with a path that is NOT registered returns `"Project not registered: ..."` (not `"No jobs found"`)
- [ ] `get_latest_audit_summary` called with a registered but never-audited project returns `"Project is registered but has no audit runs yet."`
- [ ] After Group A (scanner binaries installed), a fresh run → `get_finding_detail` for a bandit finding returns a non-null `snippet` field
- [ ] `pytest tests/ -q` — still 651+ passed, no new failures
