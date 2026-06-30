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

### `main` — HEAD: `812916a`

Working tree clean. Local `main` is 55 commits ahead of `origin/main` (no push
performed this session — not yet investigated whether a push is wanted; flag
to Yusupha before pushing).

Recent commits:
```
812916a chore: move INTEGRATION_JOURNAL.md outside git — worktrees do not share filesystem state
cef6a08 docs: add hard rule — never commit to other agents worktrees or shared coordination files
17ddb88 docs: introduce self properly in INTEGRATION_JOURNAL.md
3c0f192 chore: archive superseded docs/ content; keep PROJECT_STATE.md and AUDITOR_STANDING_INSTRUCTIONS.md tracked
5163d89 docs: move INTEGRATION_JOURNAL.md to project root
eb49553 chore: rename archive_cleanup/ to _archive/ — permanent archive of moved files
2f62284 revert: restore docs/ tracking and .nexus_secret untracking — agent made unauthorised commits
```

`docs/` contains exactly two tracked files: `PROJECT_STATE.md` and
`AUDITOR_STANDING_INSTRUCTIONS.md` (confirmed via directory listing). Everything
else is in `_archive/` at repo root, `SPECS/`, or the Obsidian vault.

### Worktrees / branches (only two exist — confirmed via `git worktree list` and `git branch -vv`)

| Path | Branch | Tip |
|------|--------|-----|
| `/home/yusupha/my_tools/nexus_audit_v3/` | `main` | `812916a` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` | `3964eda` |

All previously-tracked redundant branches (`feature/audit-trend-diff-fixqueue`,
`feature/mcp-server-sqlite-index`, `feature/trend-diff-fixqueue-mcp`,
`feature/integrate-mcp-sqlite`, `feature/f01-cycle-detection-grimp`) are gone —
deleted in the 2026-06-29 session. **Do not merge
`feature/legacy-feature-integration` into `main`** — the integration agent
requests that explicitly when a feature is ready (per coordination rules in
`INTEGRATION_JOURNAL.md`).

### `feature/legacy-feature-integration` (integration agent's branch — read-only for me)

14 commits ahead of the point it diverged; current tip `3964eda`. Verified by
reading the branch log directly (not the journal, which lags behind):

- **F-01 (circular dependency detection): COMPLETE.** Implemented in
  `5b1c19a` ("two-tier algorithm"), scope locked via `BASELINE.md` in
  `b1dd0af` (defers 8 council-suggested extensions to a future pass after
  F-02..F-12). Empirical validation against the legacy tool's historical
  output found NetworkX catches a real cycle
  (`nexus_economy.tasks` ↔ `nexus_economy.tasks.refund`) the legacy tool missed.
- **F-02 (app boundary enforcement config): IN PROGRESS.** `WHAT.md`/`DEFAULT.md`
  and council verdict/tooling-research docs committed (`3964eda`). No
  implementation code yet. Worktree has an **uncommitted** SPECS folder
  reorganisation in progress (deletions/renames under `SPECS/features/`) —
  observed via `git status --short`, not touched, read-only per Rule A1.
- `INTEGRATION_JOURNAL.md` (`/home/yusupha/my_tools/INTEGRATION_JOURNAL.md`,
  outside git) shows no reply yet from the integration agent to my prior
  introduction message (left 2026-06-29). Its File Touch Map still only
  reflects F-01 — it has not been updated for F-02 yet, so it understates
  current progress. Treat the journal as a coordination log, not a live
  status board; verify branch state directly each session.
- **Minor anomaly, not yet investigated:** a stale, pre-introduction snapshot
  of the journal (missing the "Messages" section, timestamped before the
  outside-git move) exists at `.ruff_cache/INTEGRATION_JOURNAL.md` in the
  main worktree. It's gitignored (`.ruff_cache/` is in `.gitignore`) so it
  has no git-state impact, but a markdown doc inside a linter cache directory
  is odd and worth a one-line check next session.

---

## Registered Projects (verified via `~/.nexus_audit/workspace.json`, not assumed from prior docs)

| ID (prefix) | Name | Path | Registered | `last_audited_at` | `job_history` |
|---|---|---|---|---|---|
| `501a6bc8` | NexusTestBed | `/home/yusupha/my_tests/nexus-test-target` | 2026-06-28 | `null` | empty |
| `ebd2e968` | nexus_audit_v3 | `/home/yusupha/my_tools/nexus_audit_v3` | 2026-06-28 | `null` | empty |

`active_project_id` is currently `ebd2e968` (nexus_audit_v3), **not** NexusTestBed.
**Neither project has ever had an audit run** — `job_history` is empty for both,
confirming this directly rather than trusting the prior PROJECT_STATE.md (which
incorrectly claimed NexusTestBed's registration was "lost") or the handover
(which only implied validation was outstanding).

---

## Test Suite State

**Not re-run this session.** Last reported figure (2026-06-29 handover, not
independently re-verified): 369 tests passing on an engines/infra/primitives
subset — full suite reportedly times out in this environment and must be run
in batches. `find tests -name 'test_*.py' | wc -l` shows 58 test files present.
Treat the 369 figure as provisional until re-run; do not cite it as current
fact in a merge decision without re-running.

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
| High | F-02 (boundary config) in progress on integration branch — docs only so far | Monitor via journal + direct branch reads; do not touch `default_rules.yaml` / `boundary_engine.py` independently |
| Medium | Full test suite not re-run this session — 369-passing figure is from 2026-06-29 | Re-run in batches before any merge decision |
| Low | Stray gitignored `.ruff_cache/INTEGRATION_JOURNAL.md` snapshot — origin unclear | One-line check next session, not urgent |
| Low | 55 local commits ahead of `origin/main`, unpushed | Confirm with Yusupha whether a push is wanted |

---

## Lessons Learned (carried forward — do not repeat)

1. Never use real production data/IDs in verification steps or agent prompts.
2. Never assume — ask first when unclear.
3. Agent prompts must explicitly state what NOT to do.
4. Agents must not touch production files outside stated task scope without flagging.
5. **(New, 2026-06-30) Update this file at the end of every session that changes
   git/branch/registration state — it went stale for an entire session
   (2026-06-29) despite `AUDITOR_STANDING_INSTRUCTIONS.md` being kept current
   in parallel. A status doc that isn't updated is worse than no doc, because
   it gets trusted by default at the next session's startup.**

---

## Documents in `docs/`

| File | What it covers |
|------|----------------|
| `PROJECT_STATE.md` | This file — read first every session |
| `AUDITOR_STANDING_INSTRUCTIONS.md` | Standing rules, workspace map, multi-agent isolation rules |

Everything else (layer/plugin/API refactor plans, branch audit reports, etc.)
has moved to `_archive/docs/`, `SPECS/`, or the Obsidian vault — see
`references/codebase-map.md` in the vault for the full inventory.
