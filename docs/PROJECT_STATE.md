# Nexus Audit V3 — Project State Document
**Last updated:** Session 2026-06-27
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
3. Write implementation plans to `docs/` with exact code, line references, and checklists
4. Review feature branches and approve merges to `main`
5. **Never write code to files directly** — plans go to `docs/`, agents implement, I verify

**Standing instructions and workspace map:** `docs/AUDITOR_STANDING_INSTRUCTIONS.md`
**Knowledge base:** Obsidian vault `nexus_audit_v3` (MCP: `obsidian-rest-audit-v3`)

---

## Git State

### `main` (HEAD: `27417da`)

All stabilisation work is complete. Main is clean, tested, and stable.

**Recent commits:**
```
27417da  feat(project): require --path and --name on register; prevent duplicate names/paths
8101648  feat(project): multi-ID delete, newest-first list sort, fix test teardown
6c1ee54  test: fix 47 stale tests across audit, primitives, plugins, and reports
d5e0020  test: fix stale tests — project_id, await EventBus, report engine fixtures
3494aca  merge: feature/mcp-server-sqlite-index — SQLite index, MCP server, storage fix
```

**Test suite:** 475 passed, 0 failed (last full run)

### Worktrees

| Path | Branch |
|------|--------|
| `/home/yusupha/my_tools/nexus_audit_v3/` | `main` |
| `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite/` | `feature/mcp-server-sqlite-index` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` |

### Feature Branches

| Branch | Ahead | Behind | Status |
|--------|:-----:|:------:|--------|
| `feature/legacy-feature-integration` | **14** | 15 | OPEN — active, next to review |
| `feature/f01-cycle-detection-grimp` | **7** | 16 | OPEN — subset of legacy-feature-integration |
| `feature/integrate-mcp-sqlite` | **4** | 20 | ⚠️ Subset of f01 — redundant |
| `feature/audit-trend-diff-fixqueue` | **0** | 25 | ⚠️ EMPTY — merged to main |
| `feature/mcp-server-sqlite-index` | **0** | 12 | ⚠️ EMPTY — merged to main |
| `feature/trend-diff-fixqueue-mcp` | **0** | 26 | ⚠️ EMPTY — never had work |

### Branch Decisions (confirmed this session)

Delete these four — no unique work:
- `feature/audit-trend-diff-fixqueue` — merged
- `feature/mcp-server-sqlite-index` — merged
- `feature/trend-diff-fixqueue-mcp` — never had work
- `feature/integrate-mcp-sqlite` — subset of f01

Keep these two — have unique unmerged work:
- `feature/legacy-feature-integration` — 14 commits, most advanced, active branch
- `feature/f01-cycle-detection-grimp` — 7 commits, all contained within legacy-feature-integration

**NOTE:** `feature/legacy-feature-integration` is checked out in worktree
`nexus_audit_v3_features/`. Remove worktree before deleting any branch.
`feature/mcp-server-sqlite-index` is checked out in worktree
`nexus_audit_v3-mcp-sqlite/`. Remove worktree before deleting that branch.

### Next task

1. Delete the four empty/redundant branches (remove worktrees first)
2. Review `feature/legacy-feature-integration` for merge readiness
3. Run NexusTestBed validation — register project, run fresh audit, verify findings

---

## What Was Merged This Session

### `feature/mcp-server-sqlite-index` → `main` (commit `3494aca`)

- `core/infra/audit_index.py` — per-project SQLite index at `~/.nexus_audit/projects/<id>/nexus_state.db`
- `core/mcp/` — full MCP server exposing audit data via Model Context Protocol
- `orchestrator.py` — dependency_scan now populated from real findings (not hardcoded `[]`)
- `core/mcp/tools/findings.py` — direct audit_index calls, no Orchestrator in read handlers
- 278 tests passing

### Stabilisation fixes on `main` after merge

- `core/infra/audit_index.py` — per-project path fix (pre-merge)
- `core/mcp/tools/findings.py` — Orchestrator removed from read handlers (pre-merge)
- `orchestrator.py` — dependency routing fix (pre-merge)
- Test suite — 47 stale tests fixed across infra, primitives, plugins, reports, mcp
- `core/primitives/commands/handlers/project.py` — multi-ID delete, newest-first sort
- `core/primitives/settings.py` — DuplicateNameError, duplicate path detection
- `core/primitives/commands/handlers/project.py` — `--path` and `--name` now required

---

## Outstanding Issues

| Priority | Issue | Status |
|----------|-------|--------|
| **IMMEDIATE** | Delete 4 empty branches (remove worktrees first) | Ready — confirmed this session |
| **IMMEDIATE** | Re-register NexusTestBed and run fresh audit | Workspace was cleared — project lost |
| High | Review `feature/legacy-feature-integration` for merge | 14 commits ahead, not yet reviewed |
| High | `feature/f01-cycle-detection-grimp` — decide if redundant vs canonical | Contained within legacy-feature-integration |
| Medium | NexusTestBed validation — 24 planted issues, verify detection rate | Blocked until project re-registered |
| Medium | `COUNCIL_MCP_DIRECTION_GATING.md` — empty document | Needs council run or confirm covered by MCP_SPECIFICATION.md |
| Low | `DepCache` wiring — deferred from pre-merge fixes | Own branch after legacy-feature-integration merges |
| Low | Frontend layer not yet audited | — |

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

## Worktree Rules (learned this session)

- `.venv` is in `.gitignore` — it does NOT travel with worktrees
- Each worktree needs its own fresh `pip install -e .` inside it
- NEVER copy `.venv` from one worktree to another — editable installs have hardcoded absolute paths
- The copied `.venv` causes the CLI to run code from the wrong location

---

## Lessons Learned (auditor mistakes to never repeat)

1. **Never use real production data in verification steps.** Any prompt that involves
   deletion must use throwaway test data only. Real project IDs must never appear in
   agent prompts as examples.

2. **Never assume — ask first.** If something is unclear, ask for clarification before
   writing a plan or prompt. The `.venv` vs `.gitignore` confusion this session cost
   time because I assumed instead of asking.

3. **Agent prompts must explicitly state what NOT to do.** Do not rely on the agent
   inferring limits. State: "Do NOT run any CLI commands. Do NOT register or delete
   any projects. Do NOT touch workspace.json or ~/.nexus_audit/."

4. **Agents must not touch production files without explicit authorisation.** Any
   production file change outside the stated task scope must be flagged to the auditor,
   not committed silently.

---

## Documents in `docs/`

| File | What it covers |
|------|----------------|
| `PROJECT_STATE.md` | This file — read first every session |
| `AUDITOR_STANDING_INSTRUCTIONS.md` | Standing rules, workspace map, branch register |
| `BRANCH_AUDIT_REPORT.md` | Full branch audit from 2026-06-24 |
| `JOB_HISTORY_SORT_FIX.md` | mtime sort fix — all 3 callsites fixed and merged |
| `PRE_MERGE_FIXES_MCP_SQLITE.md` | Pre-merge fix plan (in Obsidian vault projects/) |
| `KNOWN_TEST_FAILURES_MCP_SQLITE.md` | Pre-existing test failures — resolved |
| All LAYER/PLUGIN/API refactor plans | Previous session implementation plans |

---

## NexusTestBed Project

**Path:** `/home/yusupha/my_tests/nexus-test-target/`
**Status:** Project registration lost — must be re-registered
**Planted issues:** 24 (see Obsidian vault `_raw/DUMMY_PROJECT_PLAN.md`)
**Pass criteria:** ≥20/24 issues detected

**To re-register:**
```
project:register --path /home/yusupha/my_tests/nexus-test-target --name NexusTestBed
workspace:active <new ID prefix>
```
