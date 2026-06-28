# SESSION HANDOVER — Legacy Feature Integration
**Written:** 2026-06-24
**Branch:** `feature/legacy-feature-integration`
**Worktree:** `~/my_tools/nexus_audit_v3_features/`
**Read this at the start of every new session before touching anything.**

---

## What This Work Is

We extracted every feature from the legacy `nexus_audit` tool that does
not exist in `nexus_audit_v3`, documented them formally, and are now
implementing each one — properly, inside v3's architecture — one at a time.

The full feature list lives in:
`SPECS/LEGACY_FEATURE_INTEGRATION_PLAN.md` (tracked)

The sequence and working rules live in:
`SPECS/ROADMAP.md` (tracked)

---

## Non-Negotiable Working Rules

1. **Research → Spec → Implement.** In that order, always. No code before a spec exists.
2. **One feature at a time.** Do not start Feature N+1 until Feature N is merged.
3. **This worktree only.** All changes go in `nexus_audit_v3_features/`. Never touch `nexus_audit_v3/` directly.
4. **Every branch gets a `SPECS/` folder.** All `.md` files go inside it, organised by category. Nothing scattered at the root.
5. **Legacy is a reference for what, not how.** v3's plugin/engine/YAML architecture is the target — never port legacy code directly.
6. **Merge by review.** Nothing lands in `main` without being inspected first.
7. **No hardcoding.** Everything must be dynamic and project-agnostic. If a value is specific to Nexus, it belongs in config/YAML, not in source code.

---

## Worktree Map

| Path | Branch | Owner | Purpose |
|---|---|---|---|
| `~/my_tools/nexus_audit_v3/` | `main` | Yusupha | Active development. Do not touch. |
| `~/my_tools/nexus_audit_v3-mcp-sqlite/` | `feature/mcp-server-sqlite-index` | Other developer | MCP server + SQLite index. Do not touch. |
| `~/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` | Claude | This work. All changes go here. |

---

## Shared venv

The worktree has no venv of its own. Always invoke Python and pytest via:

```bash
/home/yusupha/my_tools/nexus_audit_v3/.venv/bin/python
/home/yusupha/my_tools/nexus_audit_v3/.venv/bin/pytest
```

---

## SPECS/ Folder Convention

Every branch must have a `SPECS/` folder (capital letters). All `.md` files
go inside it. Nothing is scattered at the project root. Categories:

```
SPECS/
  ROADMAP.md                       ← overall feature integration roadmap
  LEGACY_FEATURE_INTEGRATION_PLAN.md ← reference: what legacy had vs v3
  SESSION_HANDOVER.md              ← this file
  features/                        ← one file per feature (01_, 02_, etc.)
  architecture/                    ← MCP server, SQLite, system-level specs
  CLI/                             ← CLI reference and usage guides
  storage/                         ← storage research docs
```

---

## Current Position

**Phase 1 — COMPLETE.**

Feature 01 (Circular Dependency Detection) is fully done:

| Item | Status |
|---|---|
| grimp 3.14 added to pyproject.toml | ✅ |
| grimp installed in .venv | ✅ — run `pip install grimp` if venv is fresh |
| `dna_builder.py` — Python import discovery via grimp | ✅ |
| `exclude_type_checking_imports=True` — fixes false positives | ✅ |
| `dna_builder.py` — fallback to AST parser on grimp failure | ✅ |
| `dna_builder.py` — Django migrations excluded | ✅ |
| `rules_engine.py` — iterative Tarjan's SCC (no recursion risk) | ✅ |
| `rules_engine.py` — Django models self-cycle suppressed to INFO | ✅ |
| `default_rules.yaml` — import-cycle rule added and active | ✅ |
| 28/28 tests passing | ✅ |
| Dead stub functions removed from test_dna_builder.py | ✅ |
| feature/mcp-server-sqlite-index merged in | ✅ |
| SPECS/ convention enforced | ✅ |

Spec document: `SPECS/features/01_circular_dependency_detection.md`

---

**Next: Feature 02 — App Boundary Enforcement**

**What it is:** Detect when a module in one app imports directly from another
app in a way that violates the agreed architectural boundaries. v3's
`boundary_engine.py` is already well-designed — it classifies cross-app imports
as INTERNAL / HUB_APP / BOOTSTRAP / ALLOWED / VIOLATION. The problem: it has
no Nexus-specific configuration. Its `default_action` defaults to `"allow"`,
so today it silently passes everything through rather than flagging violations.

**What needs to be researched first:**
- How should Nexus's boundary rules be expressed in v3's architecture?
  In YAML rules (like the existing `default_rules.yaml`)? As a dedicated
  settings section? As a plugin? The answer must fit v3's config-driven
  design — no hardcoding of app names or file patterns in Python source.
- What are the exact exemption patterns needed?
  (hub apps, bootstrap files, signal modules, Celery task modules)
- How does `boundary_engine.py` get the config it needs at runtime?
  Who provides it — `SettingsManager`? `default_rules.yaml`? A separate file?

**Do not start implementing until the research is done and a spec is written
at `SPECS/features/02_app_boundary_enforcement.md`.**

---

## Key Technical Context

### v3 Architecture in Brief

```
cli.py          → async REPL, CommandRegistry, one event loop per session
orchestrator.py → 13-phase pipeline:
                  setup → source_sync → dna_build → fast_check →
                  load_rules → run_scanners → evaluate_rules →
                  score_apps → coupling_matrix → timeline →
                  fix_queue → git_context → write_output
plugins/        → BaseScanner subclasses, auto-discovered, run in parallel
api/            → aiohttp routes, SSE streaming with Last-Event-ID replay
core/engines/   → boundary_engine, rules_engine, scoring_engine, etc.
default_rules.yaml → YAML rules loaded by rules_engine
```

### What boundary_engine.py does today

File: `core/engines/boundary_engine.py`

- Takes a `communication_config` dict with `hub_apps`, `bootstrap_files`,
  `allowed_patterns` (fnmatch globs), and `default_action`
- Classifies every cross-app import edge as one of:
  INTERNAL / HUB_APP / FRAMEWORK / BOOTSTRAP / ALLOWED / TEST_CROSS_APP / VIOLATION
- The engine logic is sound. The problem is it receives an empty/default config
  which sets `default_action = "allow"` — meaning nothing is ever flagged.
- Nothing in the orchestrator currently populates `communication_config` with
  real values for this project.

### What the legacy tool had (reference only — do not port directly)

File: `nexus_audit/audit_engine.py`

- Hardcoded `BOOTSTRAP_LEAVES` list: asgi.py, wsgi.py, settings.py, celery.py,
  manage.py, routing.py, apps.py, admin.py
- Hardcoded Signal-module exemption (checked by keyword)
- Hardcoded Celery task-module exemption (checked by keyword)
- Hardcoded hub app definitions

These were **hardcoded for Nexus only**. The research task is to find the
right way to express these as dynamic, project-configurable values in v3.

---

## Pre-existing Test Failures (not our problem)

Running the full test suite will show ~18 failures in:
- `tests/primitives/test_events.py`
- `tests/primitives/test_commands_coverage.py`
- `tests/primitives/test_coverage_gap_fill.py`
- `tests/primitives/test_index_ext.py`

**Root cause:** `EventBus.subscribe`, `subscribe_all`, and `unsubscribe` were
made `async` in a prior commit, but these test files still call them without
`await`. These failures predate Feature 01 and are not caused by it. They are
for Yusupha to fix on `main`, not for us to touch.

**Our tests (engines/ and orchestrator/) all pass cleanly.**

---

## Git Install Commands (if starting fresh)

```bash
# Install grimp in the shared venv
cd ~/my_tools/nexus_audit_v3
.venv/bin/pip install grimp

# Verify
.venv/bin/python -c "import grimp; print(grimp.__version__)"
# Expected: 3.14
```

---

## Branch State at End of This Session

```
feature/legacy-feature-integration
  1869d61  chore: mark Feature 01 done in ROADMAP, advance to Feature 02
  57fc15f  chore: rename specs/ to SPECS/ and enforce category convention
  80aa307  chore: add settings.example.json and unignore it
  9450d31  Merge branch 'main' into feature/legacy-feature-integration
  03211e7  specs: add legacy feature integration roadmap

feature/f01-cycle-detection-grimp
  dcbe51f  merge: integrate feature/mcp-server-sqlite-index, enforce SPECS/
  fe24660  chore: rename specs/ to SPECS/ and organise into categories
  61a199c  test(f01): remove dead stub functions from test_dna_builder
  a9cc1e3  chore: save local changes before external integration (Feature 01 impl)
  2dc4979  specs(f01): circular dependency detection via grimp + iterative Tarjan SCC
```
