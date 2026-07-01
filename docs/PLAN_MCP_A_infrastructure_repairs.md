# Plan: MCP Infrastructure Repairs (Group A)
**Priority:** P0/P1 — fix these before anything else
**Written by:** Lead Code Auditor, 2026-06-30
**Agent scope:** `orchestrator.py`, `core/infra/audit_index.py`, `core/mcp/tools/audit.py`, venv package installation
**Do NOT touch:** `boundary_engine.py`, `rules_engine.py`, `dna_builder.py`, `api/routes_run.py`, anything in the integration agent's worktree

---

## Why this is Group A (the foundation)

Everything else in the MCP gap report depends on these five fixes:

- Scanner binaries not installed → 8 of 10 scanners produce zero output → no security/quality findings → scores meaningless
- `_build_summary()` strips severity/category/file from findings before SQLite insert → fix queue always empty, sub-scores always 0
- `score_security` and `score_quality` hardcoded to 0.0 in `upsert_run()` → trend data meaningless
- `git_commit` hardcoded to `"?"` in `get_trend()` → no commit attribution
- None of these blocks are waiting on the integration agent — safe to implement now

---

## Fix 1: Install scanner binaries in the venv

**Root cause:** `.venv/bin/` contains none of the scanner executables. `tool_resolver.py` resolves scanners by checking `.venv/bin/` first, then system PATH, then `python -m <tool>`. Only `ruff` is on system PATH (`/home/yusupha/.local/bin/ruff`) and is missed by the venv check. bandit, mypy, pylint, vulture, lizard, radon, and pip-audit are absent everywhere.

**Action — run these commands from the project root:**

```bash
cd /home/yusupha/my_tools/nexus_audit_v3
.venv/bin/pip install bandit mypy pylint vulture lizard radon pip-audit ruff
```

**For semgrep** (larger install, may conflict):
```bash
.venv/bin/pip install semgrep
```
If semgrep installation fails or is too large, skip it and note in a follow-up plan.

**For trufflehog** (Go binary, not pip-installable):
```bash
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sudo sh -s -- -b /usr/local/bin
```
If curl/sudo is unavailable, skip trufflehog and note it for a manual install step.

**Verify after install:**
```bash
.venv/bin/bandit --version
.venv/bin/mypy --version
.venv/bin/ruff --version
.venv/bin/pylint --version
.venv/bin/vulture --version
.venv/bin/radon --version
.venv/bin/lizard --version
.venv/bin/pip-audit --version
.venv/bin/semgrep --version  # if installed
trufflehog version             # if installed
```

**Note:** After installation, `tool_resolver.py`'s in-memory cache (negative TTL = 5 min) must be cleared before the next audit run picks up the new binaries. Either restart the server/CLI, or call `resolver.clear_cache()` explicitly. The `ToolResolver.clear_cache()` method at line 107 clears both positive and negative caches.

---

## Fix 2: `_build_summary()` strips severity/category/file from findings

**File:** `orchestrator.py`
**Method:** `_build_summary()` (find by searching for `findings_with_fp`)
**Symptom:** `get_fix_queue` always returns `{"total":0,"queue":[]}` even with `severity_floor: LOW`

**Root cause chain:**
1. `_build_summary()` emits findings with only `fingerprint` and `rule_id`
2. `upsert_run()` in `audit_index.py` reads `f.get("severity", "")` → empty string stored in SQLite
3. `get_fix_queue()` in `orchestrator.py` line ~487: `sev_rank.get("".upper(), 0)` = 0, which is below every floor rank (LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4), so every finding is filtered out
4. Result: empty queue regardless of `severity_floor`

**Current code (locate by searching `findings_with_fp`):**
```python
findings_with_fp = [
    {
        "fingerprint": f.get("fingerprint"),
        "rule_id":     f.get("rule_id"),
    }
    for f in result_data.get("findings", [])
    if f.get("fingerprint")
]
```

**Fixed code:**
```python
findings_with_fp = [
    {
        "fingerprint": f.get("fingerprint"),
        "rule_id":     f.get("rule_id"),
        "severity":    f.get("severity", ""),
        "category":    f.get("category", ""),
        "file":        f.get("file", ""),
    }
    for f in result_data.get("findings", [])
    if f.get("fingerprint")
]
```

**Why `"file"` not `"file_path"`:** The `Finding` dataclass (core/primitives/models.py line 94) uses `file` as the field name. `to_dict()` will serialise it as `"file"`. `upsert_run()` already reads `f.get("file", "")` — this is consistent.

**After this fix:** `upsert_run()` will store correct severity and category in SQLite. The fix queue filter will return findings correctly. No other changes needed to `upsert_run()` or `get_fix_queue()` for this specific bug.

---

## Fix 3: `score_security` and `score_quality` hardcoded to 0.0

**File:** `core/infra/audit_index.py`
**Function:** `upsert_run()` (find by searching `score_security = 0.0`)
**Symptom:** `security: 0.0` and `quality: 0.0` on all trend runs

**Root cause:** Lines ~75–79:
```python
score_security = 0.0
score_quality = 0.0
```
These are hardcoded. The function loads `audit_data_complete.json` into `complete_data` but never reads sub-scores from it. No derivation logic is present.

**Fix — derive sub-scores from complete data's findings:**

Replace the hardcoded lines with this derivation block, inserted directly after `complete_data` is loaded:

```python
score_security = 0.0
score_quality = 0.0

# Derive sub-scores from findings in complete data
# Simple penalty model: 1 CRITICAL = -5 pts, 1 HIGH = -3 pts, 1 MEDIUM = -1 pt, 1 LOW = -0.5 pt
# Clamped to [0, 100] starting from 100
if complete_data:
    findings_all = complete_data.get("findings", [])
    penalty_map = {"CRITICAL": 5.0, "HIGH": 3.0, "MEDIUM": 1.0, "LOW": 0.5}
    
    sec_penalty = 0.0
    qual_penalty = 0.0
    for f in findings_all:
        cat = f.get("category", "").upper()
        sev = f.get("severity", "").upper()
        p = penalty_map.get(sev, 0.0)
        if cat == "SECURITY":
            sec_penalty += p
        elif cat in ("QUALITY", "ARCHITECTURE"):
            qual_penalty += p
    
    score_security = max(0.0, 100.0 - sec_penalty)
    score_quality = max(0.0, 100.0 - qual_penalty)
```

**Note:** This penalty model is intentionally simple — it mirrors the existing `scoring_engine.py` pattern and produces meaningful non-zero numbers immediately. It does not need to match the per-app scoring engine exactly; it only needs to be non-zero and directionally correct for trend display. Once the security scanners are producing findings (Fix 1), this will show real security score degradation.

---

## Fix 4: `git_commit` hardcoded to `"?"` in trend output

**Files:** `core/infra/audit_index.py` (schema + `upsert_run`), `orchestrator.py` (`get_trend`)
**Symptom:** All trend runs show `git_commit: "?"`, `diff_runs` shows `probable_commit: null`

**Root cause:**
- The SQLite `runs` table (schema in `audit_index.py`) has no `git_commit` column
- `upsert_run()` receives `summary` from `_build_summary()` which does not include git context
- `get_trend()` in `orchestrator.py` line ~459 hardcodes `"git_commit": "?"`

**Two-part fix:**

**Part A — add `git_commit` column to the `runs` table schema in `audit_index.py`:**

In `_SCHEMA_SQL` (find by the string `CREATE TABLE IF NOT EXISTS runs`), add `git_commit TEXT DEFAULT ''` to the column list:

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT,
    timestamp INTEGER,
    job_dir TEXT,
    score_overall REAL,
    score_security REAL,
    score_quality REAL,
    findings_count INTEGER,
    HIGH_count INTEGER,
    CRITICAL_count INTEGER,
    git_commit TEXT DEFAULT ''
);
```

**Part B — populate `git_commit` in `upsert_run()`:**

`_build_summary()` does not include git context. The easiest fix is to read git context from `audit_data_complete.json` inside `upsert_run()`, which already loads that file:

After `complete_data` is loaded (same block as Fix 3 above), add:
```python
git_commit = ""
if complete_data:
    git_ctx = complete_data.get("metadata", {}).get("git_context") or {}
    git_commit = git_ctx.get("commit", "") or ""
```

Then pass `git_commit` into the `INSERT OR REPLACE` statement:
```python
conn.execute('''
    INSERT OR REPLACE INTO runs (
        run_id, project_id, timestamp, job_dir, score_overall,
        score_security, score_quality, findings_count, HIGH_count, CRITICAL_count,
        git_commit
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    run_id, project_id, ts_int, str(job_dir), score_overall,
    score_security, score_quality, findings_count, high_count, critical_count,
    git_commit
))
```

**Part C — read `git_commit` in `get_trend()` in `orchestrator.py`:**

Find `"git_commit": "?"` in the `get_trend()` method and replace with:
```python
"git_commit": r.get("git_commit", "") or "?",
```

**Migration note:** Existing SQLite databases lack the `git_commit` column. `_SCHEMA_SQL` uses `CREATE TABLE IF NOT EXISTS` which will not add columns to existing tables. The agent must also add an `ALTER TABLE` migration guard:

After the `CREATE TABLE IF NOT EXISTS runs` block, add:
```python
# Migrate: add git_commit column if not present (idempotent)
try:
    conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass  # Column already exists
```

Add this guard in both `open_index()` and `upsert_run()` where `_SCHEMA_SQL` is executed, by appending the migration to the `executescript` call or running it as a separate `execute` after.

---

## Verification checklist (auditor runs after implementation)

- [ ] `.venv/bin/bandit --version` returns a version string
- [ ] `.venv/bin/ruff --version` returns a version string
- [ ] `.venv/bin/mypy --version`, `.venv/bin/pylint --version`, `.venv/bin/vulture --version`, `.venv/bin/radon --version`, `.venv/bin/lizard --version`, `.venv/bin/pip-audit --version` all return version strings
- [ ] Run `nexus --admin` → `project:register --path /home/yusupha/my_tests/nexus-test-target --name NexusTestBed` (check registration or use existing ID `501a6bc8`)
- [ ] Run `audit:run` against NexusTestBed — watch the scanner phase output; confirm bandit, ruff, mypy, pylint, vulture, radon, lizard each appear in the phase log
- [ ] `fix:queue --severity LOW` returns at least the 1 CRITICAL circular-import finding in the queue (this validates Fix 2)
- [ ] `audit:history` → most recent run → check that `security` and `quality` sub-scores are non-zero (this validates Fix 3)
- [ ] `audit:history` → `get_trend` output shows a real git commit hash instead of `"?"` for the new run (this validates Fix 4)
- [ ] Run `pytest tests/engines/test_fix_queue.py tests/orchestrator/ tests/infra/test_audit_index.py -q` — all pass
- [ ] Run full suite `pytest tests/ -q` — still 651 passed (or more, if new scanner findings add new test coverage)
