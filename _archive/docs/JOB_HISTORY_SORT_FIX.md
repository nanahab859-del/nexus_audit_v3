# JOB_HISTORY_SORT_FIX — Implementation Plan

**Status:** INCOMPLETE — branch fixes 1 of 3 callsites. Do not merge until all 3 are fixed.
**Written by:** Lead Code Auditor
**Date:** 2026-06-24

---

## Problem

Job directories are named with random UUIDs (hex strings). Three places in the
codebase sort these with `sorted(..., reverse=True)` and no key — which sorts
alphabetically by UUID string. UUID strings are NOT chronologically ordered, so
this produces wrong results: "most recent job" resolves to whichever UUID happens
to sort last lexicographically, not the job that ran most recently.

The correct sort key is `key=lambda p: p.stat().st_mtime` (filesystem modification time).

---

## Affected Callsites

### 1. `core/primitives/commands/handlers/audit.py` — line 171

**Function:** `_handle_history()`
**Used by:** `audit:history` CLI command
**Status:** ✅ FIXED in `feature/audit-trend-diff-fixqueue` (commit `778801f`)

```python
# BEFORE (broken — alphabetical UUID sort):
jobs = sorted(history_dir.iterdir(), reverse=True)[:limit]

# AFTER (correct — mtime sort):
jobs = sorted(history_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
```

---

### 2. `core/reports/report_engine.py` — line 99

**Function:** `_load_result()`
**Used by:** `report:generate` CLI command (when no `job_id` is given — i.e. "use latest job")
**Status:** ❌ NOT FIXED — must be fixed before merge

```python
# BEFORE (broken — line 99):
candidates = sorted(jobs_dir.iterdir(), reverse=True)

# AFTER (correct):
candidates = sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
```

Full context for the agent (lines 95–112 of `core/reports/report_engine.py`):

```python
    if job_id:
        job_dir = jobs_dir / job_id
        if not job_dir.exists():
            raise FileNotFoundError(f"Job '{job_id}' not found.")
    else:
        candidates = sorted(jobs_dir.iterdir(), reverse=True)   # <-- THIS LINE
        job_dir = next(
            (d for d in candidates
             if d.is_dir() and (d / "audit_data_complete.json").exists()),
            None,
        )
        if job_dir is None:
            raise FileNotFoundError(
                "No completed audit found. "
                "Run 'audit:run' and wait for it to finish."
            )
```

The fix is a one-word change on the `candidates = sorted(...)` line.

---

### 3. `api/routes_data.py` — line 50

**Function:** `get_data()`
**Used by:** `GET /api/data` — the MCP server data endpoint (returns audit data to AI agents)
**Status:** ❌ NOT FIXED — must be fixed before merge

```python
# BEFORE (broken — line 50):
candidates = sorted(jobs_dir.iterdir(), reverse=True)

# AFTER (correct):
candidates = sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
```

Full context for the agent (lines 46–58 of `api/routes_data.py`):

```python
    candidates = sorted(jobs_dir.iterdir(), reverse=True)   # <-- THIS LINE
    job_dir = next(
        (d for d in candidates if (d / "audit_data_complete.json").exists()),
        None,
    )
    if not job_dir:
        return web.json_response(_EMPTY_DATA_RESPONSE)

    data = await read_json(job_dir / "audit_data_complete.json")
    return web.json_response(data or _EMPTY_DATA_RESPONSE)
```

---

## Implementation Instructions for Agent

Make the following two changes. Both are single-line edits. No imports needed.
No other logic changes.

### Change A — `core/reports/report_engine.py`, line 99

Find this exact line:
```
        candidates = sorted(jobs_dir.iterdir(), reverse=True)
```

Replace with:
```
        candidates = sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
```

### Change B — `api/routes_data.py`, line 50

Find this exact line:
```
    candidates = sorted(jobs_dir.iterdir(), reverse=True)
```

Replace with:
```
    candidates = sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
```

---

## Verification Checklist (for Lead Auditor after implementation)

- [ ] Read `core/reports/report_engine.py` line 99 — confirm `key=lambda p: p.stat().st_mtime` is present
- [ ] Read `api/routes_data.py` line 50 — confirm `key=lambda p: p.stat().st_mtime` is present
- [ ] Run `grep -rn "sorted.*iterdir.*reverse=True" --include="*.py"` — must return zero project hits (only `.venv` allowed)
- [ ] Confirm branch `feature/audit-trend-diff-fixqueue` has all three fixes committed
- [ ] Merge to `main` via fast-forward: `git merge --ff-only feature/audit-trend-diff-fixqueue`
- [ ] Run `pytest tests/orchestrator/ -v` — 62 tests must pass
- [ ] Run `pytest tests/integration/test_full_pipeline.py -v` — 10 tests must pass

---

## What to Do After Merge

1. Trigger a fresh `audit:run` on NexusTestBed project (`530f72b2`)
2. Confirm `audit:history` now shows the most recent run at the top
3. Run `report:generate` — confirm it uses the same recent job (not an old one)
4. Begin NexusTestBed full validation: compare findings against 24 planted issues in `DUMMY_PROJECT_PLAN.md`

---

## Note on `report_engine.py` line 78 (NOT broken)

`list_reports()` at line 78 already has the mtime sort correctly applied:
```python
return sorted(
    reports_dir.iterdir(),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
```
This line is fine — do not touch it.
