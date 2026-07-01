# Phase A — Infrastructure Repairs
**All root causes verified by Lead Auditor reading source directly. No investigation needed.**
**Implement in the order listed. Run `pytest tests/ -q` after completing all five fixes.**

---

## Fix A0: Install scanner binaries

**Why first:** Everything else depends on scanners running. The fix queue, sub-scores,
and snippets are all meaningless until findings exist.

**Root cause:** `.venv/bin/` contains none of the scanner executables. `tool_resolver.py`
resolves binaries by checking `.venv/bin/` first, then system PATH, then `python -m`
fallback. Only `ruff` is on system PATH. bandit, mypy, pylint, vulture, lizard, radon,
pip-audit, and semgrep are absent from both.

**Commands (run from your worktree `/home/yusupha/my_tools/nexus_audit_v3_mcp_fix/`):**

```bash
.venv/bin/pip install bandit mypy pylint vulture lizard radon pip-audit ruff semgrep
```

Semgrep is large. If it fails or conflicts, skip it and note in `STATUS.md`.

For trufflehog (Go binary, not pip-installable):
```bash
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
  | sudo sh -s -- -b /usr/local/bin
```
If sudo is unavailable, skip and note in `STATUS.md`.

**Verify each binary is now in `.venv/bin/`:**
```bash
for bin in bandit mypy pylint vulture lizard radon pip-audit ruff; do
    .venv/bin/$bin --version && echo "$bin OK" || echo "$bin MISSING"
done
```

**Important:** `ToolResolver` has a 5-minute negative TTL cache. After installing,
either restart the CLI/server or confirm the cache clears before the next audit run.
The `clear_cache()` method exists on `ToolResolver` if you need it programmatically.

---

## Fix A1: `_build_summary()` strips severity/category/file

**File:** `orchestrator.py`
**Find by:** searching `findings_with_fp`
**Symptom:** Fix queue always returns `{"total":0,"queue":[]}` regardless of severity floor

**Root cause chain:**
- `_build_summary()` emits findings with only `fingerprint` and `rule_id`
- `upsert_run()` reads `f.get("severity", "")` → stores empty string in SQLite
- `get_fix_queue()` does `sev_rank.get("".upper(), 0)` = 0, below every floor (LOW=1)
- Every finding filtered out

**Current code (locate by `findings_with_fp`):**
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

**Replace with:**
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

Note: `Finding` dataclass uses `file` (not `file_path`). `upsert_run()` already
reads `f.get("file", "")` — this is consistent.

---

## Fix A2: Sub-scores hardcoded to 0.0 in `upsert_run()`

**File:** `core/infra/audit_index.py`
**Find by:** searching `score_security = 0.0`
**Symptom:** `security: 0.0` and `quality: 0.0` on every trend run

**Root cause:** The function loads `audit_data_complete.json` into `complete_data`
but never reads sub-scores from it. Two lines hardcode zero.

**Find the block where `complete_data` is loaded, then replace the hardcoded
sub-score lines with this derivation:**

```python
score_security = 0.0
score_quality = 0.0

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
    score_quality  = max(0.0, 100.0 - qual_penalty)
```

---

## Fix A3: `git_commit` hardcoded to `"?"` in trend output

**Files:** `core/infra/audit_index.py` (schema + `upsert_run`) and
`orchestrator.py` (`get_trend`)

**Three-part fix:**

**Part 1 — Add `git_commit` column to schema in `audit_index.py`.**
Find `CREATE TABLE IF NOT EXISTS runs` in `_SCHEMA_SQL` and add the column:
```sql
git_commit TEXT DEFAULT ''
```

**Part 2 — Add migration guard** (existing DBs don't have the column).
After `_SCHEMA_SQL` is executed, add:
```python
try:
    conn.execute("ALTER TABLE runs ADD COLUMN git_commit TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass  # Column already exists
```
Add this guard in every function that runs `_SCHEMA_SQL`.

**Part 3 — Populate `git_commit` in `upsert_run()`.**
In the same block where `complete_data` is loaded (Fixes A1 and A2 are also here),
add after loading:
```python
git_commit = ""
if complete_data:
    git_ctx = complete_data.get("metadata", {}).get("git_context") or {}
    git_commit = git_ctx.get("commit", "") or ""
```
Then include `git_commit` in the `INSERT OR REPLACE INTO runs` statement and its
values tuple.

**Part 4 — Read `git_commit` in `get_trend()` in `orchestrator.py`.**
Find `"git_commit": "?"` and replace with:
```python
"git_commit": r.get("git_commit", "") or "?",
```

---

## After all five fixes — run these tests

```bash
cd /home/yusupha/my_tools/nexus_audit_v3_mcp_fix
pytest tests/ -q -p no:cacheprovider
```

All 651+ tests must pass. If any fail, fix them before updating `STATUS.md`.

Then run a live audit:
```bash
nexus --admin
# Inside the REPL:
project:list                          # confirm NexusTestBed shows up (prefix 501a6bc8)
audit:run --project 501a6bc8          # run a fresh scan
fix:list --severity LOW               # should return findings, not empty
audit:history --project 501a6bc8      # security/quality scores should be non-zero
```

Update `STATUS.md` with what you confirmed, then commit everything to
`feature/mcp-infrastructure-fixes`. Do not merge yourself.
