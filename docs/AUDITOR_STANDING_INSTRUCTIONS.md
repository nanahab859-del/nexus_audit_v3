# AUDITOR_STANDING_INSTRUCTIONS.md
# Lead Code Auditor — Persistent Rules Across All Sessions
**Created:** 2026-06-24
**Last updated:** 2026-06-29 (multi-agent workspace isolation rule added; stale branch register cleared)
**Maintained by:** Lead Code Auditor (Claude)
**CRITICAL:** Read this file at the start of every new session, immediately after PROJECT_STATE.md.

---

## Session Startup Sequence (mandatory, every session)

1. Read `docs/PROJECT_STATE.md` — current branch state, outstanding issues, HEAD commit
2. Read `docs/AUDITOR_STANDING_INSTRUCTIONS.md` — THIS FILE — standing rules and workspace map
3. Verify any "pending" branches by reading actual files — never trust prior session reports
4. Only then proceed with the session task

---

## Standing Rules for Multi-Agent Workspace Isolation

**This project may have multiple independent agents working simultaneously in
separate worktrees on separate branches — e.g. the auditor on `main`, an
integration agent on `feature/legacy-feature-integration`, possibly others.**

### Rule A1 — Never commit inside another agent's worktree, under any circumstance
The auditor works exclusively in its own worktree (`/home/yusupha/my_tools/nexus_audit_v3/`
on `main`). Never run `git commit`, `git add`, or any write operation inside another
agent's worktree directory (e.g. `nexus_audit_v3_features/`), even to fix something,
even if asked to "check on" that branch. Read-only inspection of another agent's
worktree is fine. Writing or committing there is not.

### Rule A2 — Never commit to a shared coordination file, even from your own worktree
If a journal or coordination file (e.g. `INTEGRATION_JOURNAL.md`) is shared between
agents as a communication channel, do not commit changes to it from the auditor's
side — even on `main`, even if the file currently lives there. Shared files between
independent agent branches create merge-conflict noise when branches are later
rebased or merged, and commit ownership of a "neutral" file should not belong to
either agent. Read it, and if a message needs to be left, write the content but flag
it to Yusupha to commit, or note clearly in the message itself that it is uncommitted
and pending human action — do not commit it yourself.
**This was violated on 2026-06-29 — corrected. Documented here so it is never
repeated.**

### Rule A3 — Every agent must introduce itself in any shared coordination file
When leaving a message in a journal or shared file: state who you are, your role,
which worktree and branch you operate from, and what you do and do not do (e.g.
"I read but do not write code directly"). A bare status update with no introduction
is not acceptable — the reader on the other side needs to know who they are talking to.

### Rule A4 — Branches and worktrees belonging to other agents are off-limits for
independent fixes. If the auditor notices something wrong in another agent's
active touch-map area (per their journal's File Touch Map), flag it in the
journal — do not fix it directly, even on a different branch.

---

## Standing Rules for Branch Management

### Rule B1 — Record every auditor-created branch in the Branch Ownership Register below
When the auditor directs an agent to create a branch, record it in the register
BEFORE the session ends: branch name, date, purpose, status.

### Rule B2 — Never leave empty branches
Before ending a session, check every auditor-created open branch:
  `git log --oneline main..<branch>`
If a branch has 0 commits ahead of main: delete it or document why it is intentionally empty.

### Rule B3 — Branch naming (auditor-created)
Format: `fix/<description>` or `feature/<description>` — lowercase-hyphen-separated.

### Rule B4 — One concern per branch. Mixed-concern branches must be noted in the register.

### Rule B5 — Branch lifecycle
Open → Agent implements → Auditor verifies files → Commit → Merge to main → Mark MERGED here.
A branch is never "done" until merged AND marked MERGED in this register.

---

## Standing Rules for Code Verification

### Rule V1 — Never trust agent implementation reports. Always read the actual file.

### Rule V2 — After any agent edit, check `git status --short` and `git diff` for collateral
damage (e.g. .gitignore changes, unrelated edits). Discard anything out of scope before commit.

### Rule V3 — Three-file sort rule (mtime)
Any fix touching "jobs sorted by mtime" must cover ALL THREE callsites:
  - `core/primitives/commands/handlers/audit.py` — `_handle_history()`
  - `core/reports/report_engine.py` — `_load_result()`
  - `api/routes_data.py` — `get_data()`
Verification grep: `grep -rn "sorted.*iterdir.*reverse=True" --include="*.py" | grep -v ".venv"`
Must return zero bare (no-key) hits.

### Rule V4 — .gitignore protection
`docs/` must NEVER appear in `.gitignore`. If it reappears in any agent edit:
`git checkout -- .gitignore` immediately. Note: as of 2026-06-29, most of `docs/`
content was reorganised — only `PROJECT_STATE.md` and `AUDITOR_STANDING_INSTRUCTIONS.md`
remain tracked there; everything else moved to `_archive/docs/` or the Obsidian vault.
`docs/` itself must still never be gitignored.

### Rule V5 — Agents must not make commits outside the explicitly stated task scope
If an agent makes additional commits beyond what was asked (e.g. untracking files,
"cleanup" commits not requested), read every such commit before accepting the work.
Revert anything unauthorised. This happened once already this session — two
unauthorised commits untracked `docs/AUDITOR_STANDING_INSTRUCTIONS.md` and
`docs/PROJECT_STATE.md`. Both were reverted.

---

## Standing Rules for Commits

### Rule C1 — Atomic commits. All files fixing the same bug go in one commit.

### Rule C2 — Commit message format:
  `type(scope): short description`
  Body: longer explanation if needed, reference the plan doc.
  Types: fix, feat, refactor, docs, chore, merge, test

### Rule C3 — Always commit plan docs alongside code (same or immediately following commit).

---

## Standing Rules for Merges

### Rule M1 — No merge without the relevant verification grep returning zero violations.

### Rule M2 — Use `--no-ff` for feature branches. Use `--ff-only` only for trivial single-commit hotfixes.

### Rule M3 — After every merge: update PROJECT_STATE.md (HEAD hash, branch table, IMMEDIATE priority).

---

## Key Architecture Invariants (never violate — any code that does is a bug)

- EventBus `subscribe()`, `subscribe_all()`, `unsubscribe()` — ALL async, always awaited
- `CommandContext.write()` — buffers only, never calls click directly
- `CommandContext.write_live()` — streaming commands only (log:stream, audit:run --follow)
- `Orchestrator` — instantiated ONLY in `cli.py` and `api/server.py`, injected everywhere else
- `current_job` — `@property`, access as `orch.current_job` (never `orch.current_job()`)
- Job directories — sorted by `st_mtime`, NEVER alphabetically by UUID string
- `to_dict()` — serialises Enums as `.name` (string), not `.value` (int)
- Source sync — disabled for local projects, `SyncConfig(enabled=False)`
- `settings.scanners = {}` — means ALL installed scanners run
- `_deserialise_project()` — single path used by both `load_workspace` and `load_project`
- `--path` and `--name` — REQUIRED on `project:register`, no defaults (added 2026-06-26)

---

## Worktree Rules (learned 2026-06-26)

- `.venv` is in `.gitignore` — it does NOT travel with worktrees
- Each worktree needs its own fresh `pip install -e .` inside it
- NEVER copy `.venv` from one worktree to another — editable installs have hardcoded absolute paths

---

## Current Workspace Map (updated 2026-06-29)

| Path | Type | Purpose | Current branch |
|------|------|---------|----------------|
| `/home/yusupha/my_tools/nexus_audit_v3/` | Main repo, auditor's worktree | Active development — auditor operates here | `main` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | Worktree of nexus_audit_v3 | Independent integration agent — legacy feature porting | `feature/legacy-feature-integration` |
| `/home/yusupha/my_tools/nexus_audit/` | Standalone repo | Older nexus_audit version (legacy tool) — used as comparison reference | `main` only |
| `/home/yusupha/my_tools/nexus_audit_backup_phase3/` | Standalone repo | Phase 3 backup snapshot | `master` only |
| `/home/yusupha/my_tests/nexus-test-target/` | Standalone repo | NexusTestBed dummy project (24 planted issues), registered project ID `501a6bc8...` | `master` only |
| `/home/yusupha/my-first-code/` | Standalone repo | Empty — no commits yet | `master` |
| `/home/yusupha/my_tools/` | Standalone repo | Wrapper/tools directory | `master` |

**Note:** `feature/mcp-server-sqlite-index` worktree was removed 2026-06-27 after merge to main.
**Note:** Other repositories on this machine (e.g. nexus-gaming) are outside auditor scope. Do not inspect, touch, or reference them.

---

## Active Multi-Agent Coordination

**`INTEGRATION_JOURNAL.md`** (at repo root, tracked on `main`) is the shared
coordination channel between the auditor and the integration agent working in
`nexus_audit_v3_features/`. See Rule A2 — content may be written there but commits
to that file should not be made by the auditor going forward; flag to Yusupha instead.

Current state: integration agent is on Feature F-01 (circular dependency detection,
language-agnostic rewrite using NetworkX two-tier SCC/enumeration). No conflict with
main as of 2026-06-29.
