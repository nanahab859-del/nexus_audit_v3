# Nexus Audit V3 — Project State Document
**Last updated:** Session 2026-06-30 (all facts verified directly from git, disk, source files)
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

## Git State (verified 2026-06-30, end of session)

### `main` — HEAD: `3d4857b`, **in sync with `origin/main`**

Working tree clean. 0/0 ahead-behind `origin/main` (pushed this session).

Recent commits:
```
3d4857b docs: full test suite verified (651/651 passing), false-positive MCP test plan, project state refresh
62bf3bd docs: refresh PROJECT_STATE.md with directly-verified state
812916a chore: move INTEGRATION_JOURNAL.md outside git — worktrees do not share filesystem state
```

`docs/` now contains seven tracked files:

| File | What it covers |
|------|----------------|
| `PROJECT_STATE.md` | This file — read first every session |
| `AUDITOR_STANDING_INSTRUCTIONS.md` | Standing rules, workspace map, multi-agent isolation rules |
| `PLAN_fix_test_pydantic_validation_async.md` | False-positive MCP test fix — awaiting agent |
| `MCP_GAPS_TRIAGE.md` | Full triage of all MCP gap issues — master assignment table |
| `PLAN_MCP_A_infrastructure_repairs.md` | Group A: P0/P1 critical infra fixes — awaiting agent |
| `PLAN_MCP_B_data_quality.md` | Group B: P1/P2 data quality fixes — awaiting agent |
| `PLAN_MCP_C_new_tools.md` | Group C: new MCP tools — awaiting agent (after Group A done) |
| `RESEARCH_integration_agent_mcp_items.md` | Items reserved for integration agent — F-02/F-05/F-06/F-09 |

### Worktrees / branches (confirmed via git, 2026-06-30)

| Path | Branch | Tip |
|------|--------|-----|
| `/home/yusupha/my_tools/nexus_audit_v3/` | `main` | `3d4857b` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` | `3964eda` (not re-checked this session — unchanged) |

**Do not merge `feature/legacy-feature-integration` into `main`** — integration agent requests that explicitly.

### `feature/legacy-feature-integration` — integration agent's branch (read-only for me)

- **F-01 (circular dependency detection): COMPLETE.** Two-tier algorithm, scope locked via `BASELINE.md`.
- **F-02 (app boundary enforcement config): IN PROGRESS.** Docs phase committed. No implementation code yet.
- Journal updated 2026-06-30 with MCP items handed over; no reply yet from integration agent.

---

## Registered Projects (verified via `~/.nexus_audit/workspace.json`)

| ID (prefix) | Name | Path | Registered | `job_history` |
|---|---|---|---|---|
| `501a6bc8` | NexusTestBed | `/home/yusupha/my_tests/nexus-test-target` | 2026-06-28 | 1 run: `17d80987` (2026-06-30) |
| `ebd2e968` | nexus_audit_v3 | `/home/yusupha/my_tools/nexus_audit_v3` | 2026-06-28 | empty |

NexusTestBed now has one run (job `17d80987`, run on 2026-06-30 this session) confirming
that all Technical Review defects are still present: 18 ghost-file findings + 1 circular-import,
all scanners except `rules_engine` silent, fix queue empty. The June-22 run data (project ID
`530f72b2`) no longer exists — that registration was deleted in a prior session. It doesn't matter;
the same bugs are confirmed live on the current registration.

---

## Test Suite State (re-run 2026-06-30, verified this session)

**651 collected, 651 passed, 0 failed, 0 skipped — single run in 80.27s.**

Corrects prior handover's claim that the suite times out and must be batched — it does not.

**Two open issues found during this run:**

1. **`tests/mcp/test_mcp_server.py::test_pydantic_validation` — confirmed false-positive test.**
   `FastMCP.get_tool()` is `async`; test calls it without `await`; all 5 assertions pass
   unconditionally regardless of whether the tools exist. Plan: `docs/PLAN_fix_test_pydantic_validation_async.md`.
   Status: **IMPLEMENTED and verified** — 51 tests pass, zero RuntimeWarning with -W error::RuntimeWarning. Plan archived to _archive/docs/.

2. `MockProc.communicate` "never awaited" warnings in two infra tests — test-mock hygiene only,
   not a production bug. Documented as out of scope in the plan above. Low priority.

---

## MCP Server — Gap Analysis (completed this session)

Based on `Nexus_Audit_MCP_Technical_Review.md` (June-22 testing session) and
`Nexus_Audit_MCP_Capability_Gap_Specification.md`, verified by reading source directly.

**Summary of confirmed root causes:**

| Issue | Root Cause (verified in source) |
|---|---|
| 8 of 10 scanners silent | None of the scanner binaries are installed in `.venv` — only `ruff` is on system PATH, missed by venv-first resolution order in `tool_resolver.py`. Bandit, mypy, pylint, vulture, lizard, radon, semgrep, pip-audit all absent. |
| Fix queue always empty | `_build_summary()` strips `severity`, `category`, `file` from findings before SQLite insert → stored as `""` → `get_fix_queue()` filter compares `sev_rank.get("", 0)=0` which is below every severity floor including LOW=1 → all filtered out |
| Sub-scores always 0.0 | `upsert_run()` in `audit_index.py` hardcodes `score_security=0.0`, `score_quality=0.0`. Loads `audit_data_complete.json` but never reads sub-scores from it |
| `git_commit: "?"` on all runs | Hardcoded string in `orchestrator.get_trend()`. No `git_commit` column in `runs` SQLite table |
| `snippet: null` on all findings | No `snippet` column in `findings` SQLite table. Scanner binaries not running (Group A prerequisite) |
| `duration_ms: 0` always | Hardcoded in `core/mcp/tools/audit.py` line ~37 with comment acknowledging it |
| Boundary violation missed | Boundary rule evaluation not running against import graph — F-02 in integration agent scope |
| 16/18 ghost-file false positives | Rule flags all files not reachable via Python imports — config files, templates, tests, dotfiles, entry points all incorrectly flagged |

**Plan documents written and committed:**

- `docs/MCP_GAPS_TRIAGE.md` — master triage, every issue assigned
- `docs/PLAN_MCP_A_infrastructure_repairs.md` — scanner install + 4 code bugs (P0/P1)
- `docs/PLAN_MCP_B_data_quality.md` — duration_ms, ghost-file FPs, dup registration, error messages, snippet storage (P1/P2)
- `docs/PLAN_MCP_C_new_tools.md` — 8 new MCP tool groups (implement after Group A done)
- `docs/RESEARCH_integration_agent_mcp_items.md` — 4 item families handed to integration agent

**Sequencing constraint:** Group A must be implemented and verified before Group C is meaningful. Group B can proceed in parallel with Group A.

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
- `project:register` — requires both `--path` and `--name`, no silent defaults
- `_deserialise_project()` — single path used by both `load_workspace` and `load_project`

---

## Outstanding Issues (prioritised)

| Priority | Issue | Status |
|---|---|---|
| **P0** | Scanner binaries not installed in `.venv` — 8/10 scanners silent | Plan: `PLAN_MCP_A_infrastructure_repairs.md` — agent needed |
| **P0** | Fix queue always empty (severity stripped in `_build_summary`) | Plan: `PLAN_MCP_A` Fix 2 — agent needed |
| **P1** | Sub-scores always 0.0 (hardcoded in `upsert_run`) | Plan: `PLAN_MCP_A` Fix 3 — agent needed |
| **P1** | `git_commit: "?"` hardcoded in `get_trend` | Plan: `PLAN_MCP_A` Fix 4 — agent needed |
| **P1** | `snippet: null` — no column in SQLite, not populated | Plan: `PLAN_MCP_B` Fix B5 (after Group A scanners run) |
| **P1** | Ghost-file rule: 16/18 findings are false positives | Plan: `PLAN_MCP_B` Fix B2 — agent needed |
| **P1** | Boundary violation (users→billing) not detected | Integration agent scope — F-02 |
| **P1** | `test_pydantic_validation` is a false-positive test | Plan: `PLAN_fix_test_pydantic_validation_async.md` — agent needed |
| **P2** | `duration_ms: 0` hardcoded in MCP tool | Plan: `PLAN_MCP_B` Fix B1 — agent needed |
| **P2** | 7 duplicate project registrations — no uniqueness check | Plan: `PLAN_MCP_B` Fix B3 — agent needed |
| **P2** | Ambiguous error messages in MCP tools | Plan: `PLAN_MCP_B` Fix B4 — agent needed |
| **P2** | 8 new MCP tool groups not yet implemented | Plan: `PLAN_MCP_C_new_tools.md` — after Group A verified |

---

## Lessons Learned (carried forward)

1. Never use real production data/IDs in verification steps or agent prompts.
2. Never assume — ask first when unclear.
3. Agent prompts must explicitly state what NOT to do.
4. Agents must not touch production files outside stated task scope without flagging.
5. Update this file at the end of every session that changes git/branch/registration state.
6. Don't repeat prior session's unverified claims as fact — re-verify performance/behavioural claims, not just state claims.
7. **(New, 2026-06-30) Root-cause bugs from source before writing plans.** Both the fix queue and
   the sub-score bugs appear in the Technical Review as symptoms. Reading `_build_summary()`,
   `upsert_run()`, and `get_fix_queue()` revealed the exact failure chain — two interacting bugs,
   not one. A plan written from the symptom alone would have fixed only the query, not the missing
   fields. Always read the code before writing the plan.
