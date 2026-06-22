# Nexus Audit v3: Implementation Handover Report

**To:** Implementation Planner / Lead Engineer
**From:** Antigravity (AI Agent)
**Authorized By:** Specification Author
**Date:** June 2026

## 1. Executive Summary
This document serves as a comprehensive handover report detailing the work completed on the Nexus Audit v3 system, discrepancies discovered between the written specifications and the `IMPLEMENTATION_PLAN.md`, and the corrective actions currently underway as authorized by the Specification Author.

---

## 2. Work Completed to Date

Following the `IMPLEMENTATION_PLAN.md`, two major phases were successfully implemented:

### Phase 1: Initial SQLite Index
- **What was done:** Created `core/infra/audit_index.py` to store audit run metadata in SQLite databases, hooked into `orchestrator.py` to `upsert_run` at the end of `_run_job`, and added the `audit:rebuild-index` CLI handler.
- **How it was done:** Implemented a "thin" SQLite schema. It captures high-level run data (`job_id`, `fleet_average`, `findings_count`) and a lightweight findings map (`fingerprint`, `run_id`, `rule_id`).
- **Why it was done this way:** The implementation strictly followed the constraint in `IMPLEMENTATION_PLAN.md` Phase 1: *"No new Orchestrator methods. diff_runs / get_trend / get_fix_queue are not touched."*

### Phase 2: MCP Server
- **What was done:** Built the FastMCP server (`core/mcp/server.py`) with strict STDIO purity and path sandboxing (`core/mcp/security.py`). 
- **Tools Implemented:** `get_server_info`, `run_project_audit`, `get_latest_audit_summary`, `get_finding_detail`, `list_findings`, `get_file_context`.
- **Tools Deferred:** `get_fix_queue`, `get_trend`, `diff_runs` (stubbed but returning "deferred").
- **CLI Extensions:** Added `mcp:config` and `mcp:status`.

---

## 3. Discrepancies Found (The "Gap Analysis")

Upon review with the Specification Author, significant gaps were identified between the `IMPLEMENTATION_PLAN.md` instructions and the master specifications (`nexus_audit_v3_storage_research.md` and `nexus_audit_v3_cli_extension.md`).

### Gap A: SQLite Architecture & Schema Discrepancy
The Storage Specification explicitly demands a **single global SQLite database** (`~/.nexus_audit/index.db`) containing complex cross-run logic:
- `first_seen_run`
- `last_seen_run`
- `status` (open / resolved / suppressed)
- `severity`, `file_path`, `category`

**The Conflict:** Because Phase 1 of the implementation plan forbade adding cross-run logic, the initial SQLite implementation defaulted to a per-project database (`projects/<id>/nexus_state.db`) and stripped out all fields requiring cross-run diffing. 
**The Impact:** Without these fields, the deferred CLI commands (like `fix:queue`) cannot function, as they rely on querying finding age and severity directly from SQLite.

### Gap B: Missing CLI Extensions & Orchestrator Methods
The following components from `nexus_audit_v3_cli_extension.md` remain unimplemented:
- **CLI Handlers:** `audit:diff`, `audit:trend`, `audit:export`, `fix:queue`.
- **Orchestrator Methods:** The underlying business logic (`diff_runs()`, `get_trend()`, `export_audit()`, `get_fix_queue()`) required to power both the CLI extensions and the deferred MCP tools.

---

## 4. Current Actions & Corrective Measures

To ensure the final product delivers the business value defined in the specifications, the **Specification Author has authorized the execution of the following corrective actions**, effectively bridging the gap between Phase 1 and the final spec:

1.  **SQLite Schema Upgrade & Migration:** 
    *   Deprecate the per-project databases and transition to the global `~/.nexus_audit/index.db` file.
    *   Expand the `runs` and `findings` tables to perfectly match the `nexus_audit_v3_storage_research.md` spec.
2.  **Advanced Upsert Logic:**
    *   Implement cross-run diffing inside `audit_index.py` during `upsert_run`. This will accurately calculate `first_seen_run`, `last_seen_run`, and finding `status` to enable age-based queueing.
3.  **Implement Missing CLI & Orchestrator Features:**
    *   Build out `audit_ext.py` and `fix_ext.py`.
    *   Implement the missing `Orchestrator` methods to supply data to both the CLI and the previously deferred MCP tools.

*Note for Implementation Planner: These actions override the Phase 1 constraint against cross-run logic, as authorized by the Specification Author, in order to fulfill the complete specification requirements.*
