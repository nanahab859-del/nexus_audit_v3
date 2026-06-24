# AUDITOR_STANDING_INSTRUCTIONS.md
# Lead Code Auditor — Persistent Rules Across All Sessions
**Created:** 2026-06-24
**Last updated:** 2026-06-24
**Maintained by:** Lead Code Auditor (Claude)
**CRITICAL:** Read this file at the start of every new session, immediately after PROJECT_STATE.md.

---

## Session Startup Sequence (mandatory, every session)

1. Read `docs/PROJECT_STATE.md` — current branch state, outstanding issues, HEAD commit
2. Read `docs/AUDITOR_STANDING_INSTRUCTIONS.md` — THIS FILE — standing rules and workspace map
3. Verify any "pending" branches by reading actual files — never trust prior session reports
4. Only then proceed with the session task

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
`docs/` must NEVER appear in `.gitignore`. Commit `bcdf324` explicitly removed it.
If it reappears in any agent edit: `git checkout -- .gitignore` immediately.

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

---

## Complete Workspace Map (audited 2026-06-24)

All git repositories found under `/home/yusupha/`:

| Path | Type | Purpose | Branches |
|------|------|---------|---------|
| `/home/yusupha/my_tools/nexus_audit_v3/` | Main repo | Active development — this project | See Branch Register below |
| `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite/` | **Worktree** of nexus_audit_v3 | Checked out on `feature/mcp-server-sqlite-index` | — (same repo) |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | **Worktree** of nexus_audit_v3 | Checked out on `feature/f01-cycle-detection-grimp` | — (same repo) |
| `/home/yusupha/my_tools/nexus_audit/` | Standalone repo | Older nexus_audit version | `main` only, 2 commits |
| `/home/yusupha/my_tools/nexus_audit_backup_phase3/` | Standalone repo | Phase 3 backup snapshot | `master` only, 2 commits |
| `/home/yusupha/nexus-gaming/` | Standalone repo | Separate project — nexus-gaming | `main` + 10 agent/experiment branches (see below) |
| `/home/yusupha/my_tests/nexus-test-target/` | Standalone repo | NexusTestBed dummy project (24 planted issues) | `master` only |
| `/home/yusupha/my-first-code/` | Standalone repo | Empty — no commits yet | `master` (no commits) |
| `/home/yusupha/my_tools/` | Standalone repo | Wrapper/tools directory | `master`, 2 commits |

---

## Branch Ownership Register — nexus_audit_v3

**Key:** AUDITOR = created by Lead Auditor (Claude) | YUSUPHA = created by Yusupha | UNKNOWN = unconfirmed

| Branch | Owner | Date | Purpose | Ahead of main | Status | Notes |
|--------|-------|------|---------|--------------|--------|-------|
| `main` | — | — | Main branch | — | ACTIVE | HEAD: `54b5fce` |
| `feature/audit-trend-diff-fixqueue` | UNKNOWN | — | Fix audit:history mtime sort + buffer clear after --follow | 0 (merged) | MERGED → `c53dc02` (2026-06-24) | **Confirm owner with Yusupha** |
| `feature/trend-diff-fixqueue-mcp` | UNKNOWN | — | Placeholder for MCP trend/diff/fixqueue work | **0 — EMPTY, behind main by 5** | STALE — empty diff, should be deleted or rebased | **Confirm owner with Yusupha** |
| `feature/f01-cycle-detection-grimp` | UNKNOWN | — | Cycle detection via grimp + SQLite/MCP work (merged with mcp-server-sqlite-index) | **10 commits ahead** | OPEN — worktree at `nexus_audit_v3_features/` | **Confirm owner with Yusupha** |
| `feature/integrate-mcp-sqlite` | UNKNOWN | — | SQLite indexing for MCP server | **10 commits ahead — IDENTICAL to f01-cycle-detection-grimp** | OPEN — same tip commit `3d40179`, appears to be same branch under two names | **Confirm owner with Yusupha** |
| `feature/mcp-server-sqlite-index` | UNKNOWN | — | MCP server SQLite index | **10 commits ahead** | OPEN — worktree at `nexus_audit_v3-mcp-sqlite/`, tip `27a2940` (4 more commits than integrate-mcp-sqlite) | **Confirm owner with Yusupha** |
| `feature/legacy-feature-integration` | UNKNOWN | — | Legacy feature integration | **4 commits ahead** | OPEN — needs inspection before merge | **Confirm owner with Yusupha** |

### nexus_audit_v3 — Findings & Questions for Yusupha

1. **`feature/trend-diff-fixqueue-mcp`** — 0 commits ahead of main, 5 behind. It is an empty branch that is now stale. Was this created by you or by the auditor? Should it be deleted?

2. **`feature/f01-cycle-detection-grimp` and `feature/integrate-mcp-sqlite`** — Both share the exact same tip commit (`3d40179`). They appear to be the same content under two branch names. Was one created as an alias of the other? Which is the canonical name to keep?

3. **`feature/mcp-server-sqlite-index`** — Has 4 more commits than the above two (tip `27a2940`), checked out in the `nexus_audit_v3-mcp-sqlite/` worktree. This appears to be the most advanced version of the SQLite/MCP work. Is this the branch the auditor should review for merge next?

4. **`feature/legacy-feature-integration`** — 4 commits ahead, last commit message is "When, throughout all iterations, what is it about?" — informal message, unclear intent. Was this your branch or the auditor's?

---

## Branch Ownership Register — nexus-gaming

**Note:** This is a separate project. The auditor's primary scope is nexus_audit_v3.
These branches are listed for awareness only.

| Branch | Owner | Ahead of main | Status | Notes |
|--------|-------|--------------|--------|-------|
| `main` | — | — | ACTIVE | HEAD: `2d5ca6d` |
| `agents/docimplementation-plan-violation-fixes` | Likely agent-created | 0 (behind 11) | STALE — fully behind main | Name suggests auto-generated by an AI agent |
| `agents/docimplementation-plan-violation-fixes-2dc2cbb4` | Likely agent-created | 0 (behind 6) | STALE — fully behind main | Appears to be a duplicate/hash-suffixed version |
| `agents/docimplementation-plan-violation-fixes-55b826b2` | Likely agent-created | 0 (behind 6) | STALE — same tip as above duplicate | Appears to be another duplicate |
| `agents/file-access-query` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Name suggests exploratory agent query, not a real feature |
| `agents/filesystem-mcp-list-all-files` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Name suggests exploratory agent query |
| `agents/list-accessible-windows-folders` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Name suggests exploratory agent query |
| `agents/list-nexus-gaming-contents` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Name suggests exploratory agent query |
| `agents/mcp-filesystem-list-untracked-files` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Name suggests exploratory agent query |
| `agents/mpc-server-usage` | Likely agent-created | 0 (behind 28) | STALE — fully behind main | Likely a typo of "mcp-server-usage" — exploratory |
| `experiment/agent-sandbox` | UNKNOWN | 0 (behind 1) | STALE — behind main | Confirm with Yusupha |

### nexus-gaming — Findings & Questions for Yusupha

All 10 non-main branches in nexus-gaming are fully behind `main` (0 commits ahead). They contain no unique work — everything in them has already been superseded by `main`. **Recommend deleting all of them** unless Yusupha has a specific reason to keep any. Confirm with Yusupha before deleting.

---

## Other Repos — Status

| Repo | Status | Action needed |
|------|--------|--------------|
| `nexus_audit` | Old version, `main` only, stable | No action — archive reference |
| `nexus_audit_backup_phase3` | Phase 3 snapshot, `master` only | No action — archive reference |
| `nexus-test-target` | Test target, `master` only | No action — used for NexusTestBed validation runs |
| `my-first-code` | Empty repo, no commits | No action |
| `my_tools` (root) | Wrapper, `master`, 2 commits | No action |
