# Nexus Audit v3: Implementation Handover Report

> **⚠ STATUS — READ BEFORE USING THIS DOCUMENT**
>
> This report is a snapshot from June 22, 2026, Session 2. Several things
> it lists as outstanding have since been resolved — it was never updated
> after that happened, so reading it in isolation will give a false
> picture. Specifically:
>
> - **Section 3 (Gap B) and Section 6 ("Outstanding Work")** claim the
>   `diff_runs`, `get_trend`, `get_fix_queue` Orchestrator methods and the
>   `audit:diff` / `audit:trend` / `audit:export` / `fix:queue` CLI
>   handlers are "not started." **They exist now.** `orchestrator.py` has
>   all three methods; `audit_ext.py`, `fix_ext.py`, and `index_ext.py`
>   are all wired into `registry.py`. This was verified directly against
>   the running branch, not assumed.
> - **Section 5, Deviation 2** ("these three tools now call real
>   Orchestrator methods") turns out to be correct, but for a reason this
>   report doesn't explain: `core/mcp/tools/findings.py` calls the
>   Orchestrator directly. Separately, `core/infra/audit_index.py` *also*
>   defines its own `get_trend`/`diff_runs`/`get_fix_queue`, querying the
>   global SQLite index instead — and those are dead code, never called
>   by anything in `core/mcp/`. This report doesn't mention that second,
>   unused implementation exists at all, which is worth knowing since
>   someone could extend or "fix" the wrong one later.
> - **The framing in Sections 1–4** — fix the bugs first, then decide on
>   the Code Owner expansion — has been reversed. The actual sequence
>   that happened: the expansion shipped, was tested end-to-end against a
>   real project through Claude Desktop, and the test confirmed the
>   underlying architecture decision needed resolving *before* any of the
>   bugs below were worth fixing, since fixing them against an unsettled
>   architecture would mean redoing some of that work anyway. That
>   resolution is now written down in `MCP_SPECIFICATION_V2.md`
>   (repository root) — read that first, not this.
>
> Everything else below — Section 4's description of what was actually
> built (the five tools, their files, the bug fixes in 4A) — is accurate
> and unchanged. Kept here in full as the historical record of what
> happened in that session.

---

**To:** Implementation Planner / Lead Engineer
**From:** Antigravity (AI Agent)
**Authorized By:** Specification Author
**Date:** June 2026 (updated: 22 June 2026 — Session 2)

---

## 1. Executive Summary

This document is a living handover report. It tracks all work completed across every session on the Nexus Audit v3 system, discrepancies between the written specifications and the codebase, corrective actions taken, and outstanding issues for the next engineer picking this up.

> **Important Note for the Next Engineer:** Some actions in Session 2 were taken without full re-reading of the master specifications each time. A verification audit is recommended before shipping. Where known deviations exist they are called out explicitly in Section 5.

---

## 2. Work Completed — Session 1 (Prior to June 22)

Following the `IMPLEMENTATION_PLAN.md`, two major phases were successfully implemented:

### Phase 1: Initial SQLite Index
- **What was done:** Created `core/infra/audit_index.py` to store audit run metadata in SQLite databases, hooked into `orchestrator.py` to `upsert_run` at the end of `_run_job`, and added the `audit:rebuild-index` CLI handler.
- **How it was done:** Implemented a "thin" SQLite schema. It captures high-level run data (`job_id`, `fleet_average`, `findings_count`) and a lightweight findings map (`fingerprint`, `run_id`, `rule_id`).
- **Why it was done this way:** The implementation strictly followed the constraint in `IMPLEMENTATION_PLAN.md` Phase 1: *"No new Orchestrator methods. diff_runs / get_trend / get_fix_queue are not touched."*

### Phase 2: MCP Server (Initial)
- **What was done:** Built the FastMCP server (`core/mcp/server.py`) with strict STDIO purity and path sandboxing (`core/mcp/security.py`).
- **Tools Implemented:** `get_server_info`, `run_project_audit`, `get_latest_audit_summary`, `get_finding_detail`, `list_findings`, `get_file_context`.
- **Tools Deferred:** `get_fix_queue`, `get_trend`, `diff_runs` (stubbed but returning "deferred").
- **CLI Extensions:** Added `mcp:config` and `mcp:status`.

---

## 3. Gaps Found After Session 1 (Pre-existing Discrepancies)

Upon review with the Specification Author, significant gaps were identified between the `IMPLEMENTATION_PLAN.md` instructions and the master specifications (`nexus_audit_v3_storage_research.md` and `nexus_audit_v3_cli_extension.md`).

### Gap A: SQLite Architecture & Schema Discrepancy
The Storage Specification explicitly demands a **single global SQLite database** (`~/.nexus_audit/index.db`) containing complex cross-run logic:
- `first_seen_run`
- `last_seen_run`
- `status` (open / resolved / suppressed)
- `severity`, `file_path`, `category`

**The Conflict:** Phase 1 of the implementation plan forbade adding cross-run logic, so the initial SQLite implementation used a per-project database (`projects/<id>/nexus_state.db`) and stripped out all fields requiring cross-run diffing.
**The Impact:** Without these fields, deferred CLI commands (like `fix:queue`) cannot function, as they rely on querying finding age and severity directly from SQLite.

### Gap B: Missing CLI Extensions & Orchestrator Methods
The following components from `nexus_audit_v3_cli_extension.md` remain unimplemented:
- **CLI Handlers:** `audit:diff`, `audit:trend`, `audit:export`, `fix:queue`.
- **Orchestrator Methods:** The underlying business logic (`diff_runs()`, `get_trend()`, `export_audit()`, `get_fix_queue()`) required to power both the CLI extensions and the deferred MCP tools.

---

## 4. Work Completed — Session 2 (June 22, 2026)

The Specification Author authorized two streams of work this session: (A) fix the MCP server's critical bugs, (B) expand MCP capabilities to cover ~45% of CLI commands.

### 4A. MCP Server — Permanent Bug Fixes

**Bug 1: Path Validation Rejecting Registered Projects**
- **Root Cause:** All MCP tools were calling `_assert_safe_path()` directly on the user-supplied `project_path`, which only accepts paths inside `~/.nexus_audit/`. This rejected legitimate source code paths like `/home/yusupha/my_tests/nexus-test-target`.
- **Fix Applied:** Created `resolve_project_id()` in `core/mcp/schemas.py`. This function accepts a project path, name, or UUID and resolves it to the internal UUID by querying the workspace registry — without touching `_assert_safe_path`. All tools now call `resolve_project_id()` first, then only use sandbox-internal paths for file I/O.
- **Files Modified:** `core/mcp/schemas.py`, `core/mcp/tools/audit.py`, `core/mcp/tools/findings.py`.

**Bug 2: `list_projects` Documented but Not Implemented**
- **Root Cause:** The tool was described in the usage guide but the `register()` function in `info.py` only contained `get_server_info`.
- **Fix Applied:** Implemented `list_projects()` in `core/mcp/tools/info.py`. It loads all projects from the workspace and returns their ID, name, and source path.
- **Files Modified:** `core/mcp/tools/info.py`.

**Bug 3: Blocking Async in FastMCP**
- **Root Cause:** Some tool functions were defined as `def` (synchronous) inside `async def register()` closures, causing them to block the event loop.
- **Fix Applied:** Converted all I/O-bound tool handlers to `async def`.
- **Files Modified:** `core/mcp/tools/audit.py`, `core/mcp/tools/findings.py`, `core/mcp/tools/info.py`.

### 4B. MCP Capability Expansion ("Code Owner" Phase)

Per the Technical Strategy Report (`specs/Nexus Audit v3 MCP Expansion.md`), five new tools were added to allow an AI agent to act as an autonomous "Code Owner" with programmatic guardrails.

**New Schemas Added (`core/mcp/schemas.py`):**
- `ScannerToggleInput` — enforces mandatory `reasoning` field (min 15 chars)
- `ScannerConfigInput` — enforces mandatory `reasoning` field
- `ProjectConfigInput` — enforces mandatory `reasoning` field
- `ReportGenerationInput` — validates output format (`md` | `json`)

**New File: `core/mcp/tools/scanners.py`**
- `enable_scanners` — toggles scanners to `True` in project SQLite config
- `disable_scanners` — toggles scanners to `False`
- `set_scanner_config` — updates strictness for a named scanner
- All three write an action log to `~/.nexus_audit/mcp_action_log.txt` for human audit trail

**New File: `core/mcp/tools/config.py`**
- `set_project_config` — patches `ProjectSettings` via `SettingsManager.patch_project_settings()`
- `generate_audit_report` — runs `ReportEngine.generate()` and writes output to `~/.nexus_audit/projects/<UUID>/audit_reports/`. Path traversal (`../`) is blocked with an explicit sandbox check.
- Both write to the same audit trail log.

**Server Registration (`core/mcp/server.py`):**
- Added `from core.mcp.tools import ..., scanners, config`
- Added `scanners.register(mcp)` and `config.register(mcp)`

### 4C. Testing

- **Test file created:** `tests/mcp/test_mcp_expansion.py`
- **Test 1 (`test_scanner_toggle_reasoning_validation`):** Verified Pydantic rejects `reasoning` fields shorter than 15 characters. ✅ PASSED
- **Test 2 (`test_report_generation_input_format`):** Verified invalid formats (`pdf`) are correctly rejected. ✅ PASSED
- **Total tool count confirmed via runtime inspection:** 15 tools registered on the live server.

---

## 5. Known Deviations & Unverified Items

> **This section is critical for the next engineer.**

### Deviation 1: Session 2 Work Was Done Without Re-Reading the Full MCP Specification
The expansion tools (`scanners.py`, `config.py`) were implemented based on the Technical Strategy Report authored by the user, without re-reading `spec/nexus_audit_v3_mcp_specification.md` in full first.

**What this means:** The tool names, input schemas, and return types may differ from what the MCP specification prescribes. Before shipping, compare the following against `nexus_audit_v3_mcp_specification.md`:
- Tool names: `enable_scanners`, `disable_scanners`, `set_scanner_config`, `set_project_config`, `generate_audit_report`
- Their Pydantic input schemas
- Their return value structures

### Deviation 2: `get_fix_queue`, `get_trend`, `diff_runs` — Implemented but Untested
These three tools now call real `Orchestrator` methods instead of returning "deferred" stubs. However, they have **not been end-to-end tested** against a real completed audit run. They may fail if the orchestrator methods expect data in formats that the current SQLite schema does not produce (see Gap A above).

### Deviation 3: Claude Desktop Caching Issue (Not a Code Bug)
During testing, Claude Desktop reported all tools as failing. **This is not a server bug.** All 15 tools are confirmed registered. The issue is that Claude Desktop was executing the old server process loaded before the fixes were applied. Fix: **fully quit and reopen Claude Desktop** to spawn a fresh MCP server process.

---

## 6. Outstanding Work (Not Yet Implemented)

| Item | Source | Status |
|---|---|---|
| SQLite schema upgrade to global `index.db` | `nexus_audit_v3_storage_research.md` | ❌ Not started |
| Cross-run diffing / `first_seen_run` / `last_seen_run` | `nexus_audit_v3_storage_research.md` | ❌ Not started |
| `audit:diff`, `audit:trend`, `audit:export` CLI handlers | `nexus_audit_v3_cli_extension.md` | ❌ Not started |
| `fix:queue` CLI handler | `nexus_audit_v3_cli_extension.md` | ❌ Not started |
| End-to-end test for `get_fix_queue`, `get_trend`, `diff_runs` MCP tools | This session | ❌ Not done |
| Verify expansion tool schemas against MCP spec | `nexus_audit_v3_mcp_specification.md` | ❌ Not done |

---

## 7. File Change Summary (Session 2)

| File | Change |
|---|---|
| `core/mcp/schemas.py` | Added `resolve_project_id()`, `ScannerToggleInput`, `ScannerConfigInput`, `ProjectConfigInput`, `ReportGenerationInput` |
| `core/mcp/tools/info.py` | Implemented `list_projects()` |
| `core/mcp/tools/audit.py` | Fixed path resolution, converted to `async` |
| `core/mcp/tools/findings.py` | Fixed path resolution, converted to `async` |
| `core/mcp/tools/scanners.py` | **NEW FILE** — `enable_scanners`, `disable_scanners`, `set_scanner_config` |
| `core/mcp/tools/config.py` | **NEW FILE** — `set_project_config`, `generate_audit_report` |
| `core/mcp/server.py` | Registered new `scanners` and `config` tool modules |
| `tests/mcp/test_mcp_expansion.py` | **NEW FILE** — schema guardrail tests (2 passed) |
| `mcp_usage_guide.md` | Full rewrite with accurate WSL↔Windows config, tool reference |
| `specs/mcp_vs_cli_capabilities.md` | **NEW FILE** — CLI vs MCP capability comparison |
| `specs/mcp_capability_expansion_game_report.md` | **NEW FILE** — architectural case for expansion |
