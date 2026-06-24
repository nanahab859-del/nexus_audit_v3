# Nexus Audit V3 — Project State Document
**Last updated:** Session 2026-06-24
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

---

## Codebase Architecture

```
nexus_audit_v3/
    cli.py                          Entry point — interactive REPL
    orchestrator.py                 13-phase audit job runner
    server.py                       MCP/aiohttp server entry point
    core/
        primitives/
            commands/               CLI command routing (package, not single file)
                context.py          CommandContext — pure data carrier, write_live() for streaming
                registry.py         CommandRegistry — routes commands
                parser.py           CommandParser — argparse wrapper, never sys.exit
                handlers/           One module per command group
                    audit.py        audit:run/cancel/status/history
                    scanner.py      scanner:list(4-col)/enable(multi)/disable(multi)
                    project.py      project:register/list/info/delete
                    workspace.py    workspace:status/active
                    config.py       config:get/set/show/export
                    fix.py          fix:list/show/mark/note
                    report.py       report:generate/history
                    log.py          log:stream (write_live, asyncio.shield on unsubscribe)
                    system.py       system:help/version/status, exit
                    ai.py           ai:* (documented stubs)
                    _utils.py       resolve_project_id() — prefix matching helper
            models.py               All dataclasses — to_dict() uses .name for Enums
            events.py               EventBus — ALL methods are async def
            atomic.py               Crash-safe JSON I/O, raises on corrupt files
            security.py             Random-key Fernet encryption, no hostname derivation
            settings.py             SettingsManager — _deserialise_project() single path
        infra/
            git_utils.py            Shared run_git() — has asyncio.wait_for timeout
            utils.py                Shared deep_merge()
            audit_logger.py         Async subscribe/unsubscribe, clears buffer after flush
            config_loader.py        asyncio.to_thread for YAML loading
            file_discovery.py       Excludes by rel_path AND filename (two-pass)
            language_detection.py   EXTENSION_MAP (single canonical dict)
            registry.py             PluginRegistry — stores _bus for reload()
            tool_resolver.py        5-min negative TTL, clear_cache(), TOOL_PIP_PACKAGE
            key_pool.py             Round-robin, mark_rate_limited() on 429 only
            source_sync.py          Credential file (not URL token injection)
            dep_cache.py            atexit save, async context manager
            git_context.py          imports run_git from git_utils
            fast_check.py           imports run_git from git_utils
        engines/
            dna_builder.py          AST (Python) + regex (JS), handles node.module=None
            rules_engine.py         YAML rules, _evaluate_pattern logs warning
            scoring_engine.py       Ghost = not imported by anything (no imports==0 check)
            boundary_engine.py      Cross-app import violations
            coupling.py             N×N coupling matrix
            timeline.py             count >= num_available for PERSISTENT
            fix_queue.py            Public: load(), entries(), get_entry() with prefix match
        reports/
            __init__.py             Exports ReportEngine
            report_engine.py        Finds job by st_mtime, routes to generators
            markdown_report.py      Accepts result_data dict, not Job object
            json_report.py          JSON format
    plugins/
        base.py                     asyncio.wait_for on communicate(), list() copy before extend
        generic_script_scanner.py   _executable instance attr, _run_dynamic_tool with timeout
        security/                   bandit, semgrep, secretscrub, trufflehog, django_settings
        quality/                    ruff, mypy, pylint, vulture(code>1), radon, lizard, djlint(code>1)
        dependency/                 pip_audit (renamed from safety), license_audit
        architecture/               lizard
    api/
        server.py                   sm=SettingsManager(); orchestrator=Orchestrator(sm); bus=orchestrator.bus
        routes_run.py               start_job()/cancel_job() — correct method names
        routes_data.py              Reads from jobs/ dir by mtime; .state.value for enum
        routes_stream.py            await subscribe_all/unsubscribe; event.payload (not .data)
        routes_project.py           Credential file for git token, not URL embedding
        routes_settings.py          load_workspace()/save_workspace() throughout
        routes_config.py            core.infra.config_loader import path (correct)
        routes_ai.py                load_workspace()/save_workspace() throughout
    docs/                           All implementation plans — tracked in git
    tests/                          62 orchestrator tests, 10 integration tests — all passing
```

---

## Key Design Decisions

- **EventBus methods are all async** — `subscribe()`, `subscribe_all()`, `unsubscribe()` must always be awaited
- **`CommandContext.write()` only buffers** — `write_live()` is for streaming commands only
- **`Orchestrator` created in `cli.py` and `api/server.py` only** — injected everywhere else via constructor
- **Job directories sorted by `st_mtime`** — NOT alphabetically (UUID hex does not sort chronologically)
- **`current_job` is a `@property`** — access as `orch.current_job`, never `orch.current_job()`
- **Source sync disabled for local projects** — `SyncConfig(enabled=False)`, no project copying
- **`settings.scanners = {}` means all installed scanners run** — orchestrator default logic handles this
- **`to_dict()` serialises Enums as `.name`** (string not int) — JSON files use enum name strings
- **Single deserialisation path** — `_deserialise_project()` used by both `load_workspace` and `load_project`

---

## Git Branch State

### `main` (HEAD: `bcdf324`)
All planned work is on main. Last commit restored `docs/`.

### Feature Branches

| Branch | Tip Commit | What it does | Merge status |
|--------|-----------|-------------|-------------|
| `feature/audit-trend-diff-fixqueue` | `778801f` | Fixes `audit:history` sort by mtime; clears stdout buffer after --follow | **BLOCKED — needs 2 more fixes before merge (see JOB_HISTORY_SORT_FIX.md)** |
| `feature/trend-diff-fixqueue-mcp` | `b6b4d78` | Same as main tip — placeholder for MCP trend/diff work | Inspect before merge |
| `feature/f01-cycle-detection-grimp` | `3d40179` | Cycle detection via `grimp` library | Inspect before merge |
| `feature/integrate-mcp-sqlite` | `3d40179` | SQLite indexing for MCP server (shares tip with f01) | Inspect before merge |
| `feature/mcp-server-sqlite-index` | `822bbba` | MCP server SQLite index (different from integrate-mcp-sqlite) | Inspect before merge |
| `feature/legacy-feature-integration` | `888fd75` | Legacy feature integration — scope unclear | Inspect before merge |

### Merge Order

1. `feature/audit-trend-diff-fixqueue` — **after** agent fixes the two remaining sort callsites
2. Inspect `trend-diff-fixqueue-mcp`, `mcp-server-sqlite-index`, `integrate-mcp-sqlite`
3. Resolve overlap between `f01-cycle-detection-grimp` and `integrate-mcp-sqlite`
4. `legacy-feature-integration` last — needs full inspection

---

## Outstanding Issues

| Priority | Issue | Status |
|----------|-------|--------|
| **IMMEDIATE** | `audit:history` sort bug fixed in branch, but `report_engine.py:99` and `api/routes_data.py:50` still use alphabetical UUID sort | Agent must fix 2 lines, then merge branch — see `JOB_HISTORY_SORT_FIX.md` |
| High | Full NexusTestBed validation — run audit, compare 24 planted issues against findings | Blocked until sort fix merged |
| Medium | Frontend layer not yet audited | — |
| Low | AI module stubs — planned, not yet implemented | — |

---

## All Documents in `docs/`

| File | What it covers |
|------|----------------|
| `PROJECT_STATE.md` | This file — always read first in new sessions |
| `LAYER1_CLI_COMMAND_REFACTOR.md` | commands/ package restructure |
| `LAYER1_PRIMITIVES_REFACTOR.md` | settings.py, security.py, models.py |
| `LAYER1_EVENTS_ATOMIC_REFACTOR.md` | events.py async + atomic.py |
| `LAYER2_INFRA_REFACTOR.md` | All 12 infra files |
| `LAYER3_ENGINES_REFACTOR.md` | Orchestrator + 6 engine files |
| `LAYER4_REPORTS_REFACTOR.md` | Report layer |
| `PLUGINS_REFACTOR.md` | All 13 scanner plugins |
| `API_BACKEND_REFACTOR.md` | All 8 API route files |
| `DUMMY_PROJECT_PLAN.md` | 24 planted issues at nexus_test_project/ |
| `SCANNER_AND_HISTORY_IMPROVEMENTS.md` | scanner:list columns, multi-enable/disable |
| `ORCHESTRATOR_AND_HISTORY_FIXES.md` | Phase reporting, default scanners |
| `STATIC_AUDIT_FIXES.md` | Static audit — 10 fixes, 14 files |
| `POST_AUDIT_MINOR_FIXES.md` | Comments fix + double cleanup fix |
| `JOB_HISTORY_SORT_FIX.md` | mtime sort fix — 3 callsites total; 1 fixed in branch, 2 remain |

---

## NexusTestBed Test Project

**Path:** `/home/yusupha/my_tests/nexus-test-target/`
**Project ID prefix:** `530f72b2`
**Planted issues:** 24 (see `docs/DUMMY_PROJECT_PLAN.md`)
**Pass criteria:** ≥20/24 issues detected, ghost file flagged, boundary violation found

**Validation status:** Sort fix needed before re-running — current history shows wrong job.
