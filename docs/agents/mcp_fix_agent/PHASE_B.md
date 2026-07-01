# Phase B — Data Quality Fixes
**Implement after Phase A is complete and verified by the Lead Auditor.**
**All root causes verified by Lead Auditor reading source directly.**

---

## Fix B1: `duration_ms: 0` hardcoded in MCP tool

**File:** `core/mcp/tools/audit.py`
**Find by:** searching `duration_ms`
**Symptom:** Every MCP audit response reports zero duration — impossible to detect
hung or stale scans

**Root cause:** Comment in source acknowledges it: `# not easily available without
diffing timestamps`. Both `started_at` and `finished_at` exist in
`audit_data_complete.json` under `metadata.started_at` / `metadata.finished_at`
as ISO strings.

**Fix:** In the `run_project_audit` tool function, after loading `audit_summary.json`,
also load `audit_data_complete.json` from the same directory to compute duration:

```python
duration_ms = 0
complete_path = summary_path.parent / "audit_data_complete.json"
if complete_path.exists():
    try:
        with open(complete_path, "r") as cf:
            complete = json.load(cf)
        meta = complete.get("metadata", {})
        started  = meta.get("started_at")
        finished = meta.get("finished_at")
        if started and finished:
            from datetime import datetime
            s  = datetime.fromisoformat(started.replace("Z", "+00:00"))
            fi = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            duration_ms = int((fi - s).total_seconds() * 1000)
    except Exception:
        pass
```

Replace the hardcoded `"duration_ms": 0` line in the return dict with
`"duration_ms": duration_ms`.

---

## Fix B2: Ghost-file rule flags config files, templates, docs as ghost files

**File:** `core/engines/rules_engine.py`
**Method:** `_evaluate_ghost()` — line 154
**Symptom:** 16 of 18 ghost-file findings are false positives: `pyproject.toml`,
`audit_rules.yaml`, `.eslintrc.json`, `templates/index.html`, `app.py`, etc.

**Root cause (auditor traced to source):**
- `language_detection.py` maps `.yaml`, `.toml`, `.json`, `.html`, `.md`, `.sh`,
  `.jinja`, `.css`, `.scss` as recognised languages
- `dna_builder.py` adds ALL of these to `dna.modules` / `dna.physical_files`
- `_evaluate_ghost()` builds `imported_by` from `dna.physical_files` — so YAML,
  TOML, JSON, HTML files all appear as candidates
- `default_rules.yaml` has `languages: ["*"]` for the ghost-file rule — all
  languages pass the language filter
- These files have zero importers by definition → all flagged

**DO NOT touch `default_rules.yaml`** — integration agent's active F-02 territory.

**Fix — add a language guard in `_evaluate_ghost()` at line ~166:**

Add this constant near the top of `rules_engine.py` (after imports):
```python
# Languages where "not imported by anything" is meaningful.
# Non-importable file types (config, templates, docs) are excluded from ghost-file detection.
_IMPORTABLE_LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "typescript"})
```

In `_evaluate_ghost()`, after the existing `__init__.py` exclusion check and
before the `rule.languages` check, add:
```python
# Skip file types that cannot be imported (config, templates, docs, etc.)
if mod and mod.language not in _IMPORTABLE_LANGUAGES:
    continue
```

The full condition block after the fix:
```python
for file_path, importers in imported_by.items():
    if not importers:
        if any(b in file_path for b in bootstrap): continue
        if file_path.endswith("__init__.py"): continue
        if file_path not in dna.physical_files: continue

        mod = next((m for m in dna.modules.values() if m.relative_path == file_path), None)
        if not mod: continue

        # NEW: skip non-importable file types
        if mod.language not in _IMPORTABLE_LANGUAGES:
            continue

        if rule.languages and rule.languages != ["*"] and mod.language not in rule.languages:
            continue

        findings.append(create_finding(...))
```

**Expected result after fix:** A fresh NexusTestBed audit should produce at most
2 ghost-file findings: `billing/subscriptions.py` and `src/ghost.py` (the two
intentionally planted ghost modules). Everything else should be excluded.

---

## Fix B3: Duplicate project registration — no uniqueness check

**File:** Find the `project:register` command handler.
Run: `grep -rn "project.*register\|register.*project" /home/yusupha/my_tools/nexus_audit_v3_mcp_fix/core/primitives/commands/handlers/ --include="*.py"`

**Root cause:** `project:register` does not check for an existing entry with the
same path or name before inserting.

**Fix — add a pre-check before calling `sm.register_project()`:**
```python
existing = [
    p for p in sm.load_workspace().projects
    if str(p.settings.project_path) == str(resolved_path)
    or p.name.lower() == name.lower()
]
if existing:
    ctx.write(
        f"[warn] A project with this path or name already exists: "
        f"{existing[0].name} (ID {existing[0].id[:8]}). "
        f"Use project:list to see all registered projects."
    )
    return
```

---

## Fix B4: Ambiguous error messages in MCP tools

**File:** `core/mcp/tools/audit.py` — `get_latest_audit_summary` and any other
tool returning `{"error": "No jobs found"}`

**Fix — return specific messages for each failure case:**

```python
@mcp.tool()
async def get_latest_audit_summary(input: ProjectInput) -> dict:
    try:
        project_id = await resolve_project_id(input.project_path)
    except Exception:
        return {
            "error": f"Project not registered: {input.project_path}",
            "hint": "Run: nexus --admin → project:register --path <path> --name <name>"
        }

    jobs_dir = Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"
    if not jobs_dir.exists() or not any(jobs_dir.iterdir()):
        return {
            "error": "Project is registered but has no audit runs yet.",
            "hint": "Call run_project_audit to start a scan."
        }
    # ... rest of function unchanged
```

Apply the same pattern to any other tool that currently returns a bare
`"No jobs found"` string.

---

## Fix B5: `snippet: null` — no snippet column in SQLite

**File:** `core/infra/audit_index.py`
**Note:** Snippet data will be populated once Phase A scanner binaries run.
This fix adds the storage layer — snippets appear automatically after the next audit.

**Part 1 — add `snippet TEXT` column to `findings` table schema:**
Find `CREATE TABLE IF NOT EXISTS findings` in `_SCHEMA_SQL`. Add column:
```sql
snippet TEXT DEFAULT ''
```

**Part 2 — migration guard** (existing DBs):
```python
try:
    conn.execute("ALTER TABLE findings ADD COLUMN snippet TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass  # Column already exists
```
Add in every function that executes `_SCHEMA_SQL`.

**Part 3 — populate snippet in `upsert_run()`:**
Build a fingerprint→snippet lookup from `complete_data`:
```python
fp_to_snippet: dict = {}
if complete_data:
    for f in complete_data.get("findings", []):
        fp   = f.get("fingerprint")
        snip = f.get("snippet")
        if fp and snip:
            fp_to_snippet[fp] = snip[:500]  # cap at 500 chars
```

Pass the snippet into `INSERT` and `UPDATE` statements for the `findings` table.

**Part 4 — surface `snippet` in MCP tool responses:**
Find `list_findings` and `get_finding_detail` tools. Add `snippet` to their
SELECT queries and include it in the returned dict.

---

## After all Phase B fixes — verify

```bash
cd /home/yusupha/my_tools/nexus_audit_v3_mcp_fix
pytest tests/ -q -p no:cacheprovider
```

All tests must pass. Then run a fresh audit against NexusTestBed and verify:
- `duration_ms` in the MCP response is a positive integer
- Ghost-file findings reduced to ≤ 2 (only `billing/subscriptions.py` and `src/ghost.py`)
- `project:register` with a duplicate path returns a warning, not a second entry
- `get_latest_audit_summary` with an unregistered path returns a clear error message

Update `STATUS.md`, commit to `feature/mcp-infrastructure-fixes`. Do not merge yourself.
