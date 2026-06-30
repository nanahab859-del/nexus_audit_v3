# Nexus Audit V3 — Project State Document
**Last updated:** Session 2026-06-30 (auditor verified all facts below directly
against git, disk, and `workspace.json` — not copied from prior session's report)
**Maintained by:** Lead Code Auditor (Claude)
**Project path:** `\\wsl.localhost\Ubuntu-22.04\home\yusupha\my_tools\nexus_audit_v3\`

---

## What This Project Is

`nexus_audit_v3` is a local-first code quality audit tool. It scans Python,
JavaScript, and TypeScript projects using a fleet of static analysis scanners,
scores each "app" (subdirectory) against a fleet baseline, tracks findings over
time, and surfaces a prioritised fix queue. It exposes two interfaces: an
interactive CLI (`nexus --admin`) and an MCP server (`server.py`) for AI agents.

---

## My Role

I am the **Lead Code Auditor and Architecture Reviewer**. My responsibilities:

1. Read the codebase directly — never trust implementation reports without verifying files
2. Identify bugs, architectural violations, and quality issues
3. Write implementation plans to `docs/` or the Obsidian vault with exact code, line references, and checklists
4. Review feature branches and approve merges to `main`
5. **Never write code to files directly** — plans go to `docs/`/vault, agents implement, I verify

**Standing instructions and workspace map:** `docs/AUDITOR_STANDING_INSTRUCTIONS.md`
**Knowledge base:** Obsidian vault `nexus_audit_v3` (MCP: `obsidian-rest-audit-v3`)
**Session handovers:** vault `projects/SESSION_HANDOVER_*.md` — read the latest one first, every session

---

## Git State (verified by reading git directly, 2026-06-30)

### `main` — HEAD: `62bf3bd`, **pushed and in sync with `origin/main`**

Working tree clean. `git rev-list --left-right --count origin/main...main` → `0  0`
after pushing this session (was 56 commits ahead, unpushed, at session start).

Recent commits:
```
62bf3bd docs: refresh PROJECT_STATE.md with directly-verified state
812916a chore: move INTEGRATION_JOURNAL.md outside git — worktrees do not share filesystem state
cef6a08 docs: add hard rule — never commit to other agents worktrees or shared coordination files
17ddb88 docs: introduce self properly in INTEGRATION_JOURNAL.md
3c0f192 chore: archive superseded docs/ content; keep PROJECT_STATE.md and AUDITOR_STANDING_INSTRUCTIONS.md tracked
5163d89 docs: move INTEGRATION_JOURNAL.md to project root
eb49553 chore: rename archive_cleanup/ to _archive/ — permanent archive of moved files
```

`docs/` contains three tracked files: `PROJECT_STATE.md`,
`AUDITOR_STANDING_INSTRUCTIONS.md`, and (new, 2026-06-30)
`PLAN_fix_test_pydantic_validation_async.md` (see Test Suite State below).
Everything else is in `_archive/` at repo root, `SPECS/`, or the Obsidian vault.

### Worktrees / branches (only two exist — confirmed via `git worktree list` and `git branch -vv`)

| Path | Branch | Tip |
|------|--------|-----|
| `/home/yusupha/my_tools/nexus_audit_v3/` | `main` | `62bf3bd` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` | `3964eda` (unchanged this session) |

All previously-tracked redundant branches (`feature/audit-trend-diff-fixqueue`,
`feature/mcp-server-sqlite-index`, `feature/trend-diff-fixqueue-mcp`,
`feature/integrate-mcp-sqlite`, `feature/f01-cycle-detection-grimp`) are gone —
deleted in the 2026-06-29 session. **Do not merge
`feature/legacy-feature-integration` into `main`** — the integration agent
requests that explicitly when a feature is ready (per coordination rules in
`INTEGRATION_JOURNAL.md`).

### `feature/legacy-feature-integration` (integration agent's branch — read-only for me)

Not re-checked this session (no changes expected this fast — last verified
2026-06-30 earlier in this same session, tip `3964eda`):

- **F-01 (circular dependency detection): COMPLETE.** Implemented in
  `5b1c19a` ("two-tier algorithm"), scope locked via `BASELINE.md` in
  `b1dd0af` (defers 8 council-suggested extensions to a future pass after
  F-02..F-12). Empirical validation against the legacy tool's historical
  output found NetworkX catches a real cycle
  (`nexus_economy.tasks` ↔ `nexus_economy.tasks.refund`) the legacy tool missed.
- **F-02 (app boundary enforcement config): IN PROGRESS.** `WHAT.md`/`DEFAULT.md`
  and council verdict/tooling-research docs committed (`3964eda`). No
  implementation code yet. Worktree had an **uncommitted** SPECS folder
  reorganisation in progress as of last check — observed via `git status
  --short`, not touched, read-only per Rule A1.
- `INTEGRATION_JOURNAL.md` (`/home/yusupha/my_tools/INTEGRATION_JOURNAL.md`,
  outside git) still shows no reply from the integration agent to my prior
  introduction message (left 2026-06-29). Treat the journal as a coordination
  log, not a live status board; verify branch state directly each session.

---

## Registered Projects (verified via `~/.nexus_audit/workspace.json`, not assumed from prior docs)

| ID (prefix) | Name | Path | Registered | `last_audited_at` | `job_history` |
|---|---|---|---|---|---|
| `501a6bc8` | NexusTestBed | `/home/yusupha/my_tests/nexus-test-target` | 2026-06-28 | `null` | empty |
| `ebd2e968` | nexus_audit_v3 | `/home/yusupha/my_tools/nexus_audit_v3` | 2026-06-28 | `null` | empty |

`active_project_id` is currently `ebd2e968` (nexus_audit_v3), **not** NexusTestBed.
**Neither project has ever had an audit run** — `job_history` is empty for both.
This is still the single biggest outstanding item — see below.

---

## Test Suite State — re-run in full this session (2026-06-30)

**Result: 651 collected, 651 passed, 0 failed, 0 skipped.**

Ran per-directory first (all 9 subdirs of `tests/`, each clean), then
confirmed with one single full-suite run: `651 passed in 80.27s`. This
**corrects** the 2026-06-29 handover's claim that "the full suite times out
and must be run in batches" — it does not, at least not in this environment/
session. Per-directory breakdown:

| Directory | Passed | Notes |
|---|---|---|
| `tests/primitives` | 165 | clean |
| `tests/commands` | 9 | clean |
| `tests/engines` | 83 | clean |
| `tests/infra` | 121 | 5 warnings, see below |
| `tests/plugins` | 103 | clean |
| `tests/reports` | 86 | clean |
| `tests/mcp` | 8 | 5 warnings, **1 real bug found**, see below |
| `tests/orchestrator` | 66 | clean |
| `tests/integration` | 10 | 234 warnings (3rd-party deprecation, see below), 50.5s |
| **Total** | **651** | |

### Findings from this run

1. **Confirmed bug — `tests/mcp/test_mcp_server.py::test_pydantic_validation`
   is a false-positive test.** `FastMCP.get_tool()` is `async` (verified via
   `inspect.iscoroutinefunction`); the test calls it without `await` and
   asserts `is not None`. An unawaited coroutine object is never `None`, so
   all 5 assertions pass unconditionally regardless of whether the named
   tools actually exist — the test currently provides zero real coverage of
   MCP tool registration. Full root-cause and exact fix written to
   `docs/PLAN_fix_test_pydantic_validation_async.md`. **Not yet implemented**
   — needs an agent (per my role, I don't edit test files myself).
2. **Test-hygiene only, not a production bug** — `RuntimeWarning: coroutine
   'MockProc.communicate' was never awaited` in
   `tests/infra/test_fast_check.py::test_run_git_command_terminate_exception`
   and `tests/infra/test_git_context.py::test_get_git_context_timeout`.
   Traced to those tests' own `mock_wait_for` stub raising `TimeoutError`
   without awaiting/closing the coroutine passed into it. The real
   `core/infra/git_utils.py:run_git()` is correct — real `asyncio.wait_for`
   always awaits-or-cancels its argument. Low priority, not blocking
   anything; noted in the plan doc as explicitly out of scope for the
   `test_pydantic_validation` fix.
3. **Third-party deprecation noise** — 234 `DeprecationWarning`s from
   `pathspec`'s `GitWildMatchPattern` (should be `GitIgnoreBasicPattern` /
   `GitIgnoreSpecPattern`), surfacing repeatedly in `tests/integration` and
   once in `tests/infra/test_file_discovery.py`. Not our code; only
   actionable if/when `pathspec` is upgraded. No action taken.

---

## Key Architecture Invariants (never violate)

- EventBus `subscribe()`, `subscribe_all()`, `unsubscribe()` — ALL async, always awaited
- `CommandContext.write()` — buffers only, never calls click directly
- `CommandContext.write_live()` — streaming commands only
- `Orchestrator` — instantiated ONLY in `cli.py` and `api/server.py`, injected everywhere else
- `current_job` — `@property`, access as `orch.current_job` (never `orch.current_job()`)
- Job directories — sorted by `st_mtime`, NEVER alphabetically by UUID
- `to_dict()` — serialises Enums as `.name` (string not int)
- Source sync — disabled for local projects, `SyncConfig(enabled=False)`
- `settings.scanners = {}` — means ALL installed scanners run
- `_deserialise_project()` — single path used by both `load_workspace` and `load_project`
- `--path` and `--name` — REQUIRED on `project:register`, no defaults

---

## Outstanding Issues

| Priority | Issue | Status |
|----------|-------|--------|
| **IMMEDIATE** | NexusTestBed validation never run — `job_history` confirmed empty | Both projects registered, ready; no run attempted yet |
| High | `test_pydantic_validation` is a false-positive test (see Test Suite State) | Plan written: `docs/PLAN_fix_test_pydantic_validation_async.md` — needs an agent to implement, then I verify |
| High | F-02 (boundary config) in progress on integration branch — docs only so far | Monitor via journal + direct branch reads; do not touch `default_rules.yaml` / `boundary_engine.py` independently |
| Low | `MockProc.communicate` unawaited-coroutine warnings in 2 infra tests | Test hygiene only, not a production bug; deprioritised, documented in the plan doc as out of scope |

**Resolved this session:** unpushed commits (pushed, `main`/`origin/main` now
in sync at `62bf3bd`); stray gitignored `.ruff_cache/INTEGRATION_JOURNAL.md`
snapshot (deleted, confirmed no other stray copies exist anywhere in the
repo); full test suite re-run (651/651 passing, see above).

---

## Lessons Learned (carried forward — do not repeat)

1. Never use real production data/IDs in verification steps or agent prompts.
2. Never assume — ask first when unclear.
3. Agent prompts must explicitly state what NOT to do.
4. Agents must not touch production files outside stated task scope without flagging.
5. Update this file at the end of every session that changes git/branch/
   registration state — it went stale for an entire session (2026-06-29)
   despite `AUDITOR_STANDING_INSTRUCTIONS.md` being kept current in parallel.
   A status doc that isn't updated is worse than no doc, because it gets
   trusted by default at the next session's startup.
6. **(New, 2026-06-30) Don't repeat a prior session's unverified claims as
   fact.** The "full suite times out" claim from 2026-06-29 was wrong (or at
   least no longer true) — a single full run took 80s. Re-verify
   performance/behavioural claims, not just state claims, before restating them.

---

## Documents in `docs/`

| File | What it covers |
|------|----------------|
| `PROJECT_STATE.md` | This file — read first every session |
| `AUDITOR_STANDING_INSTRUCTIONS.md` | Standing rules, workspace map, multi-agent isolation rules |
| `PLAN_fix_test_pydantic_validation_async.md` | Fix for the false-positive MCP test found 2026-06-30 — awaiting an agent |

Everything else (layer/plugin/API refactor plans, branch audit reports, etc.)
has moved to `_archive/docs/`, `SPECS/`, or the Obsidian vault — see
`references/codebase-map.md` in the vault for the full inventory.
