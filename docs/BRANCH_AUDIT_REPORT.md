# BRANCH_AUDIT_REPORT.md
# Nexus Audit V3 — Full Branch & Workspace Audit
**Date:** 2026-06-24
**Produced by:** Lead Code Auditor (Claude)
**Source:** Direct git inspection — all data read from live filesystem, not from prior reports.

---

## 1. Workspace Map — nexus_audit_v3 Only

The project lives in one git repository with three working directories:

| Working Directory | Type | Branch checked out |
|------------------|------|--------------------|
| `/home/yusupha/my_tools/nexus_audit_v3/` | Primary checkout | `main` |
| `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite/` | Git worktree | `feature/mcp-server-sqlite-index` |
| `/home/yusupha/my_tools/nexus_audit_v3_features/` | Git worktree | `feature/f01-cycle-detection-grimp` |

These are NOT separate repositories. They are three views into the same `.git` folder,
each checked out on a different branch simultaneously. Edits in one worktree are
immediately visible to git from any other.

---

## 2. All Branches — Summary Table

| Branch | Ahead of main | Behind main | Status | Worktree |
|--------|:------------:|:-----------:|--------|----------|
| `main` | — | — | ACTIVE (HEAD: `02fe50b`) | `/nexus_audit_v3/` |
| `feature/mcp-server-sqlite-index` | **10** | 7 | OPEN — active work | `/nexus_audit_v3-mcp-sqlite/` |
| `feature/f01-cycle-detection-grimp` | **10** | 7 | OPEN — active work | `/nexus_audit_v3_features/` |
| `feature/integrate-mcp-sqlite` | **10** | 7 | OPEN — ⚠️ IDENTICAL to f01 (same tip commit) | none |
| `feature/legacy-feature-integration` | **4** | 6 | OPEN — active work | none |
| `feature/audit-trend-diff-fixqueue` | **0** | 6 | ⚠️ EMPTY — merged into main today, no longer ahead | none |
| `feature/trend-diff-fixqueue-mcp` | **0** | 7 | ⚠️ EMPTY — zero commits ahead of main | none |

Remote tracking: `origin/main` and `origin/feature/mcp-server-sqlite-index` exist on remote.
All other branches are local only.

---

## 3. Branch-by-Branch Detail

---

### BRANCH: `feature/mcp-server-sqlite-index`
**Worktree:** `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite/`
**Ahead of main:** 10 commits | **Behind main:** 7 commits
**Tip commit:** `27a2940` — docs: write session handover for fresh-session restart

#### What this branch is doing
This is the most advanced of the three active feature branches. It is implementing
two tightly coupled capabilities in sequence:

**Phase 1 — SQLite Audit Index** (`core/infra/audit_index.py`, 396 lines added)
A persistent SQLite database that indexes every finding from every audit run,
enabling fast queries across historical data without re-reading all JSON files.
The index stores findings by severity, category, scanner, and file, and supports
prefix-matched job ID lookups.

**Phase 2 — MCP Server** (`core/mcp/` package, ~300 lines added)
A Model Context Protocol server that exposes Nexus audit data to external AI
agents (Claude Desktop, Cursor). The MCP layer sits on top of the SQLite index
and provides structured tools: `audit`, `findings`, `scanners`, `config`, `info`.
The MCP server is a separate entry point from the existing aiohttp API server.

**CLI extensions** (`core/primitives/commands/handlers/audit_ext.py`, `fix_ext.py`,
`index_ext.py`, `mcp.py`) — new CLI commands for controlling the index and MCP server.

**Spec documents** reorganized into `SPCES/` directory (note: typo in folder name —
`SPCES` not `SPECS`, and `MPC` not `MCP` — worth fixing before merge).

#### Commit history (newest first)
```
27a2940  docs: write session handover for fresh-session restart
9c27c50  chore: move cli_reference.md to SPCES/CLI directory
a263aec  refactor: reorganize documentation into Active/ directory
d3f5f2f  docs: consolidate MCP specs, fix interrupted file move
822bbba  Update specs and remove test_tools.py
c542404  docs: reconcile MCP read-only spec and Code Owner expansion
e0feb3d  feat: add mcp server and sqlite index
9e4e57a  feat: implement MCP server (Phase 2)
f2c8993  feat: implement SQLite audit index (Phase 1)
5407add  docs: summary and implementation plan for SQLite + MCP server
```

#### Files changed vs main (44 files, +7,670 lines net)
- **New source:** `core/infra/audit_index.py`, entire `core/mcp/` package (9 files),
  4 new CLI handler files, `orchestrator.py` extended (+124 lines)
- **Modified source:** `core/primitives/commands/registry.py`, `pyproject.toml`
- **New tests:** 9 test files covering MCP, index, CLI extensions, orchestrator
- **New specs/docs:** 15 files under `SPCES/` directory

#### Notes
- The session handover document (`SPCES/SESSION_HANDOVER.md`) records that `main` was
  never to be touched directly — this branch's work is for review and merge by you.
- The branch is 7 commits behind main, meaning the sort fixes merged today are not yet
  in this branch. It will need rebasing or merging from main before final integration.
- `dna_builder.py` and `rules_engine.py` are NOT modified in this branch (unlike f01).

---

### BRANCH: `feature/f01-cycle-detection-grimp`
**Worktree:** `/home/yusupha/my_tools/nexus_audit_v3_features/`
**Ahead of main:** 10 commits | **Behind main:** 7 commits
**Tip commit:** `3d40179` — Merge branch 'feature/mcp-server-sqlite-index' into feature/integrate-mcp-sqlite

#### What this branch is doing
This branch has a more complex history. It started as the specification and
implementation of circular dependency detection (Feature 01), then pulled in
the full `feature/mcp-server-sqlite-index` branch via a merge commit. So it
currently contains EVERYTHING that `feature/mcp-server-sqlite-index` contains,
PLUS the circular dependency work.

**Circular dependency detection** (`specs/features/01_circular_dependency_detection.md`,
changes to `core/engines/dna_builder.py` and `core/engines/rules_engine.py`):

The spec identifies two bugs in v3's current cycle detection:

1. **Recursive DFS crash risk** — `rules_engine.py::_evaluate_cycle` uses recursive
   Python DFS. On a project with an import chain deeper than ~1,000 modules it raises
   `RecursionError` and silently drops ALL rule findings for that run. Legacy had this
   exact bug and explicitly fixed it with an iterative Tarjan SCC algorithm. v3
   reintroduced it. This branch replaces the recursive DFS with iterative Tarjan SCC.

2. **`TYPE_CHECKING` imports counted as real dependencies** — `dna_builder.py` uses
   `ast.walk()` unconditionally, so `if TYPE_CHECKING: from x import y` is treated as
   a real runtime import, creating false-positive cycles that do not exist at runtime.
   This branch adds TYPE_CHECKING block exclusion to the import parser.

Additionally, no `cycle` rule exists in `default_rules.yaml` on main, so the cycle
detector never runs regardless. This branch adds the rule.

#### Commit history (newest first)
```
3d40179  Merge branch 'feature/mcp-server-sqlite-index' into feature/integrate-mcp-sqlite
822bbba  Update specs and remove test_tools.py
a9cc1e3  chore: save local changes before external integration
c542404  docs: reconcile MCP read-only spec and Code Owner expansion
e0feb3d  feat: add mcp server and sqlite index
9e4e57a  feat: implement MCP server (Phase 2)
f2c8993  feat: implement SQLite audit index (Phase 1)
5407add  docs: summary and implementation plan for SQLite + MCP server
2dc4979  specs(f01): circular dependency detection via grimp + iterative Tarjan SCC
03211e7  specs: add legacy feature integration roadmap
```

#### Files changed vs main (49 files, +7,929 lines net)
Superset of `mcp-server-sqlite-index` plus:
- `core/engines/dna_builder.py` modified (+102 lines, -? — TYPE_CHECKING fix)
- `core/engines/rules_engine.py` modified (+135 lines — iterative Tarjan SCC)
- `default_rules.yaml` modified (+9 lines — cycle rule added)
- `tests/engines/test_dna_builder.py` modified (+116 lines)
- `tests/engines/test_rules_engine.py` modified (+109 lines)
- Specs for circular dependency detection

#### Relationship to `feature/integrate-mcp-sqlite`
Both branches share tip commit `3d40179` exactly. They are the same content
under two names. `feature/integrate-mcp-sqlite` appears to be a branch that
was used as the merge TARGET when pulling `mcp-server-sqlite-index` into this
work — the merge commit message says "Merge branch 'feature/mcp-server-sqlite-index'
into feature/integrate-mcp-sqlite". The `f01` branch was then pointed at that
same merge commit. They are now identical.

---

### BRANCH: `feature/integrate-mcp-sqlite`
**Worktree:** none
**Ahead of main:** 10 commits | **Behind main:** 7 commits
**Tip commit:** `3d40179` — same as `feature/f01-cycle-detection-grimp`

#### What this branch is doing
**Identical content to `feature/f01-cycle-detection-grimp`.** Same commit history,
same diff vs main, same tip. This appears to be the intermediate integration branch
that was used to merge `mcp-server-sqlite-index` into `f01`'s lineage — it was the
named target in the merge commit, and after the merge both branch pointers ended up
at the same commit.

It is not a separate feature. It is the merge staging area that f01 used to pull
in the SQLite/MCP work. No unique work exists here that is not already in f01.

---

### BRANCH: `feature/legacy-feature-integration`
**Worktree:** none (but the ROADMAP says it belongs in `nexus_audit_v3_features/` —
that worktree is currently on f01, not this branch)
**Ahead of main:** 4 commits | **Behind main:** 6 commits
**Tip commit:** `888fd75` — "When, throughout all iterations, what is it about?"

#### What this branch is doing
This branch is doing a **systematic gap analysis between the old `nexus_audit` (legacy)
and `nexus_audit_v3`**, identifying every feature that existed in legacy that has not
yet been ported to v3, and building a phased implementation plan.

The gap analysis (read directly from `docs/LEGACY_FEATURE_INTEGRATION_PLAN.md`, 211 lines)
identified 12 missing or incomplete features. The two highest-priority ones are the
same bugs that `feature/f01-cycle-detection-grimp` is also working on (circular
dependency detection and dna_builder TYPE_CHECKING). This is not a conflict — they
are coordinated: the roadmap in this branch is the planning document, f01 is the
implementation.

**What this branch has actually implemented so far:**
- `core/engines/dna_builder.py` — modified (TYPE_CHECKING import exclusion, same fix as f01)
- `core/engines/rules_engine.py` — modified (iterative Tarjan SCC for cycle detection)
- `default_rules.yaml` — cycle rule added
- `settings.example.json` — new file, example settings for documentation
- `specs/01_circular_dependency_detection.md` — feature spec
- `specs/ROADMAP.md` — 12-feature phased roadmap
- `docs/LEGACY_FEATURE_INTEGRATION_PLAN.md` — full legacy vs v3 gap analysis
- `.gitignore` modified — ⚠️ adds entries, needs review before merge

#### Commit history (newest first)
```
888fd75  When, throughout all iterations, what is it about?  (informal message)
80aa307  chore: add settings.example.json and unignore it
9450d31  Merge branch 'main' into feature/legacy-feature-integration
03211e7  specs: add legacy feature integration roadmap
```

#### Notes
- The tip commit message (`888fd75` — "When, throughout all iterations, what is it about?")
  is informal and does not describe what the commit actually does. Before review/merge,
  the actual content of that commit should be inspected.
- This branch merged from `main` at commit `9450d31` to stay in sync, which is the
  correct approach (merge main in, not rebase, to preserve history).
- The `.gitignore` modification needs to be carefully checked — the `docs/` removal
  from `.gitignore` was a deliberate recent fix and must not be re-introduced.

---

### BRANCH: `feature/audit-trend-diff-fixqueue`
**Worktree:** none
**Ahead of main:** 0 commits | **Behind main:** 6 commits
**Status:** ⚠️ EMPTY — this branch's work was merged into main today

#### What happened
This branch contained the `audit:history` mtime sort fix and the stdout buffer
clear after `--follow` streaming. Both were merged into main in this session
(commit `c53dc02`). The branch pointer was not moved — it now points behind main
with nothing unique. It is a closed branch that has served its purpose.

---

### BRANCH: `feature/trend-diff-fixqueue-mcp`
**Worktree:** none
**Ahead of main:** 0 commits | **Behind main:** 7 commits
**Status:** ⚠️ EMPTY — zero commits ahead of main, never had work committed to it

#### What this branch was for
Based on the name and the session handover document found in `mcp-server-sqlite-index`,
this was intended as a placeholder for work on trend analysis, diff reporting, and
fix-queue features exposed via MCP. The session handover explicitly says:
"feature/trend-diff-fixqueue-mcp is their own, separate work — explicitly not your scope."
No commits were ever made to it beyond its branch point.

---

## 4. Cross-Branch Relationships

The three active feature branches are NOT independent — they are coordinated:

```
main
  │
  ├─── feature/legacy-feature-integration
  │      └── Planning doc + gap analysis + Phase 1 specs
  │          (the "what needs to be built" branch)
  │
  ├─── feature/mcp-server-sqlite-index          ←─── origin remote tracks this
  │      └── SQLite index + MCP server implementation
  │          (the "new infrastructure" branch)
  │
  └─── feature/f01-cycle-detection-grimp
         └── Circular dep detection + TYPE_CHECKING fix
             + PULLED IN mcp-server-sqlite-index via merge
             (the "integration" branch — contains both f01 work AND mcp-sqlite work)

feature/integrate-mcp-sqlite = same as f01 (merge staging artifact, identical tip)
```

The design intent (from reading the roadmap): `legacy-feature-integration` drives
the planning. Each feature gets its own branch. `mcp-server-sqlite-index` delivers
the infrastructure. `f01` delivers Feature 01 (circular deps) and has already
absorbed the infrastructure work via merge. The remaining 11 features from the
roadmap have not yet been branched.

---

## 5. What the Auditor Needs to Know Before Any Future Merge

1. **`feature/mcp-server-sqlite-index`** — has the cleanest, most up-to-date version
   of the SQLite/MCP code. 7 commits behind main (sort fixes not yet incorporated).
   Needs review of all new code in `core/mcp/` and `core/infra/audit_index.py`.

2. **`feature/f01-cycle-detection-grimp`** — contains f01 + the SQLite/MCP work merged
   in. The unique f01 work (iterative Tarjan SCC, TYPE_CHECKING exclusion) touches
   `dna_builder.py` and `rules_engine.py`. These are the same files the auditor
   has already reviewed on main — the changes here must be diffed carefully.

3. **`feature/legacy-feature-integration`** — the `.gitignore` change must be reviewed
   before merge. The `dna_builder.py` and `rules_engine.py` changes here overlap with
   f01 — needs a three-way comparison (main, f01, legacy-integration) to confirm they
   are doing the same thing or to catch divergence.

4. **`feature/integrate-mcp-sqlite`** — no action needed. It is identical to f01.

5. **`feature/audit-trend-diff-fixqueue`** and **`feature/trend-diff-fixqueue-mcp`**
   — both empty (0 commits ahead of main). Flagged but not deleted. No action until
   you decide what to do with them.
