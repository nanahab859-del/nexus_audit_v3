# MCP Gap Report — Issue Triage & Assignment
**Auditor:** Lead Code Auditor (Claude)
**Triage date:** 2026-06-30
**Source documents:** `Nexus_Audit_MCP_Technical_Review.md`, `Nexus_Audit_MCP_Capability_Gap_Specification.md`
**Based on:** Live reading of `orchestrator.py`, `core/infra/audit_index.py`, `core/mcp/tools/audit.py`, `core/infra/tool_resolver.py`, `core/primitives/models.py` and NexusTestBed job data from a fresh June 30 run — the June 22 run IDs in the Technical Review are from a now-deleted registration (`530f72b2`) but the same 19-finding pattern repeats on the current run, confirming all issues are still present.

---

## Key clarification on data provenance

The Technical Review was run against project ID `530f72b2-0836-4aed-8eee-fc7bd1c10c76`. That
registration no longer exists. The current NexusTestBed registration is `501a6bc8-a3e5-42ab-b6ba-ff50b3b09b43`.
A fresh audit run on June 30 against the current registration produced **identical symptoms**: 18
ghost-file findings + 1 circular-import, all scanners except `rules_engine` silent, fix queue empty.
**Every defect described in the Technical Review is still present.** The lost run data affects nothing
— the bugs are in the code, not the data.

---

## Multi-agent isolation rule (read before assigning any work)

The integration agent on `feature/legacy-feature-integration` is working through **F-01 through F-12**
(see `SPECS/FEATURE_INVENTORY.md` in that worktree). Before assigning any item to a new
implementation agent, check this table to avoid collision.

**Contact channel:** `/home/yusupha/my_tools/INTEGRATION_JOURNAL.md` (outside git, shared file).
**Rule:** If an item touches a file the integration agent is actively modifying, do NOT assign it
to a new agent without first confirming via the journal that it's safe.

---

## Triage table — all issues from the Technical Review

| # | Issue | Priority | Root Cause (verified by reading source) | Assignment |
|---|---|---|---|---|
| 1 | 8 of 10 scanners silent | **P0** | Scanner binaries not installed in `.venv` — only `ruff` is on system PATH. `tool_resolver.py` looks in venv bin dir first, then system PATH, then `python -m` fallback. None of them find bandit, mypy, pylint, vulture, lizard, radon, semgrep, pip-audit. | **NEW AGENT** — Group A plan |
| 2 | `get_fix_queue` always returns `{"total":0,"queue":[]}` | **P0** | `_build_summary()` in `orchestrator.py` line ~382 only emits `fingerprint` and `rule_id` per finding — strips `severity`, `category`, `file`. `upsert_run()` stores `severity=""` in SQLite. `get_fix_queue()` filters by `sev_rank.get("".upper(), 0)` = 0, which is below every floor rank including LOW=1, so every finding is filtered out. | **NEW AGENT** — Group A plan |
| 3 | No secret scanner detecting secrets | **P0** | No `secretscrub` or `trufflehog` binary present. Trufflehog is a Go binary (not pip-installable). `secretscrub` is a custom scanner in the plugins — needs its binary dependency installed. | **NEW AGENT** — Group A plan (scanner install step) |
| 4 | `security: 0.0` and `quality: 0.0` on every run | **P1** | `upsert_run()` in `audit_index.py` hardcodes `score_security = 0.0` and `score_quality = 0.0` (lines ~75–79). Loads `audit_data_complete.json` but never reads sub-scores from it. No derivation logic present. | **NEW AGENT** — Group A plan |
| 5 | `snippet: null` on all findings | **P1** | SQLite `findings` table has no `snippet` column. `_build_summary()` doesn't include snippet. Bandit/semgrep (main snippet producers) are not running. **Depends on issue #1 being fixed first to get meaningful snippets.** | **NEW AGENT** — Group B plan (add column; snippets populate once scanners run) |
| 6 | `git_commit: "?"` on all runs | **P1** | `get_trend()` in `orchestrator.py` line 459 hardcodes `"git_commit": "?"`. The `runs` SQLite table has no `git_commit` column. `git_ctx` is captured and saved to `audit_data_complete.json` but never persisted to SQLite. | **NEW AGENT** — Group A plan |
| 7 | Boundary violation `users→billing` not detected | **P1** | The boundary rule evaluation logic is not implemented/not being evaluated against the import graph. This is **F-02 in the integration agent's active workstream** (`feature/legacy-feature-integration`). | **INTEGRATION AGENT** — research note only |
| 8 | 16 of 18 ghost-file findings are false positives | **P1** | Ghost-file rule flags any file not reachable via Python imports. Config files (`pyproject.toml`, `audit_rules.yaml`, `.eslintrc.json`), template files, test files, and tool metadata files are all being flagged. Rule needs exclude patterns. | **NEW AGENT** — Group B plan |
| 9 | `duration_ms: 0` on every audit run | **P2** | `core/mcp/tools/audit.py` line 37 explicitly hardcodes `"duration_ms": 0` with comment `# not easily available without diffing timestamps`. Both `started_at` and `finished_at` are in `audit_data_complete.json`. | **NEW AGENT** — Group B plan |
| 10 | 7 duplicate project registrations | **P2** | No uniqueness constraint or pre-check on (name, path) in `project:register`. `SettingsManager.register_project()` does not validate for duplicates. | **NEW AGENT** — Group B plan |
| 11 | Ambiguous `{"error":"No jobs found"}` | **P2** | Error message returned for multiple distinct cases: wrong path, project found but no runs, no matching run ID. Cannot distinguish without reading source. | **NEW AGENT** — Group B plan |

---

## Triage table — new MCP tools proposed in the reports

| # | Tool Group | Proposed Tools | Overlap Check | Assignment |
|---|---|---|---|---|
| T1 | Code Intelligence | `get_snippet_by_hash`, `get_code_block`, `get_file_lines` | None — F-01..F-12 don't cover snippet retrieval tools | **NEW AGENT** — Group C plan (after Group A done) |
| T2 | Git & Commit Tracking | `get_commit_diff`, `blame_finding`, `get_branch_findings` | None | **NEW AGENT** — Group C plan |
| T3 | Working Sub-Score Engine | `get_score_breakdown`, `get_category_trend` | None | **NEW AGENT** — Group C plan |
| T4 | Secret & Credential Detection | `scan_secrets`, `list_credential_patterns` | None | **NEW AGENT** — Group C plan |
| T5 | Dependency CVE Scanning | `scan_dependencies`, `get_cve_report`, `get_cvss_scores` | F-05 (Dependency Freshness & Risk Cache) is in integration agent scope. The new MCP tools here overlap directly with F-05's CVE output format. | **INTEGRATION AGENT** — research note only |
| T6 | Cross-Service Dependency Map | `get_dependency_graph`, `list_shared_modules`, `get_service_impact` | F-06 (Dependency Graph Visualisation) and F-07 (Coupling Map UI) are in integration agent scope. | **INTEGRATION AGENT** — research note only |
| T7 | Audit Engine Health Check | `get_job_manifest`, `get_scan_duration`, `verify_fresh_run` | None | **NEW AGENT** — Group C plan |
| T8 | Audit Log MCP Access | `get_job_log`, `list_scanner_output`, `get_scanner_errors` | None | **NEW AGENT** — Group C plan |
| T9 | API Contract Validation | `validate_api_contracts`, `diff_openapi_specs` | None in F-01..F-12 | **NEW AGENT** — Group C plan (P3, lowest priority) |
| T10 | Finding Suppression Management | `suppress_finding`, `list_suppressions`, `get_suppression_reason` | None | **NEW AGENT** — Group C plan |
| T11 | Boundary Rule Evaluation | `get_boundary_violations`, `list_boundary_rules` | **F-02 is explicitly this** — integration agent is in the docs phase of F-02 right now. | **INTEGRATION AGENT** — research note only |
| T12 | Fix Queue API/UI | `PATCH /api/fix-queue/{id}`, `GET /api/fix-queue` | **F-09** in integration agent scope | **INTEGRATION AGENT** — research note only |

---

## Plan documents written

| Document | Covers | Status |
|---|---|---|
| `docs/PLAN_MCP_A_infrastructure_repairs.md` | Issues #1 #2 #3 #4 #6 (P0/P1 critical) | Written 2026-06-30 |
| `docs/PLAN_MCP_B_data_quality.md` | Issues #5 #8 #9 #10 #11 (P1/P2) | Written 2026-06-30 |
| `docs/PLAN_MCP_C_new_tools.md` | T1 T2 T3 T4 T7 T8 T9 T10 (new MCP tools) | Written 2026-06-30 |
| `docs/RESEARCH_integration_agent_mcp_items.md` | Issues #7 + T5 T6 T11 T12 (integration agent territory) | Written 2026-06-30 |

**Sequencing constraint:** Group A must be implemented and verified (scanners producing findings, fix queue populated) before Group B's snippet storage is meaningful and before Group C new tools are worth building. Group B and Group A can otherwise be implemented in parallel.
