# Plan: New MCP Tools (Group C)
**Priority:** P0/P1/P2/P3 — implement AFTER Group A infrastructure repairs are complete and verified
**Written by:** Lead Code Auditor, 2026-06-30
**Agent scope:** `core/mcp/tools/` (new tool files), `core/mcp/server.py` (registration), `core/infra/audit_index.py` (any new queries needed)
**Do NOT touch:** Anything in the integration agent's worktree. The tools in this plan are confirmed not to overlap with F-01..F-12.

**Prerequisite:** Group A must be implemented and verified first. Until scanners run and findings are populated with severity/category/snippet, several tools here (especially Code Intelligence) will return limited data even if correctly implemented.

---

## Background — what belongs in this plan vs. what doesn't

The Technical Review proposed 10+ new tool groups. After triage against F-01..F-12:

- **In this plan:** Code Intelligence, Git Tracking, Sub-Score Engine, Secret Detection, Audit Health Check, Audit Log MCP Access, Finding Suppression, API Contract Validation
- **NOT in this plan (integration agent scope):** Dependency CVE Scanning (F-05), Cross-Service Dependency Map (F-06/F-07), Fix Queue API/UI (F-09), Boundary Violation tools (F-02)

See `docs/RESEARCH_integration_agent_mcp_items.md` for the handover to the integration agent.

---

## New Tool Group 1 (P0): Audit Engine Health Check

**Why P0:** `duration_ms: 0` means there is currently no way for a caller to confirm a fresh scan actually ran vs. returning a cached result. This must be fixed before any audit result can be trusted.

**Note:** Fix B1 in `docs/PLAN_MCP_B_data_quality.md` fixes `duration_ms` in `run_project_audit`. This tool group is the MCP-level complement — exposing per-scanner detail that Fix B1 cannot.

**Tools to implement:**

### `get_job_manifest`
Returns a structured manifest of the most recent audit job: file count scanned, per-scanner status (ran / skipped / errored), per-scanner duration, overall start/end timestamps, and job ID.

```python
@mcp.tool()
async def get_job_manifest(input: ProjectInput) -> dict:
    """Returns the execution manifest for the latest audit job."""
```

Data source: `audit_data_complete.json` → `metadata` section. Currently the metadata has `started_at`, `finished_at`, `total_findings`, but no per-scanner breakdown. **The orchestrator must be updated to add a `scanner_results` list to metadata before this tool has data to return** — see implementation note below.

### `verify_fresh_run`
Returns `{"fresh": true, "run_id": "...", "age_seconds": 42}` — confirming the most recent run is not stale (i.e., completed in the last N minutes and duration_ms > 0).

```python
@mcp.tool()
async def verify_fresh_run(input: ProjectInput, max_age_minutes: int = 30) -> dict:
    """Confirms the latest audit run is fresh (completed within max_age_minutes and has non-zero duration)."""
```

**Implementation note for the orchestrator change:** In `orchestrator.py`, `_build_result()` should add to `metadata`:
```python
"scanner_results": [
    {
        "scanner": scanner_name,
        "status": "ran" | "skipped" | "not_found",
        "findings_count": N,
        "duration_ms": T
    }
    for scanner_name, result in scanner_run_results.items()
]
```
The agent must find where scanner results are collected in the orchestrator's scan phase and pass them through `_build_result()`. This is a small orchestrator change but is required for `get_job_manifest` to be meaningful.

---

## New Tool Group 2 (P0): Code Intelligence

**Why P0:** Every finding returns `snippet: null`. Without code context, a finding is not actionable without manually opening the file.

**Depends on:** Group A (scanner binaries installed) for snippets to exist, and Group B Fix B5 (snippet stored in SQLite).

**Tools to implement:**

### `get_snippet_by_hash`
Returns the code snippet stored for a specific finding fingerprint.

```python
@mcp.tool()
async def get_snippet_by_hash(input: FindingHashInput) -> dict:
    """Returns the stored code snippet for a finding identified by its fingerprint hash."""
    # Query: SELECT snippet, file_path, severity, category FROM findings WHERE fingerprint = ?
```

### `get_code_block`
Returns N lines of source code around a file/line reference directly from the source file on disk.

```python
@mcp.tool()
async def get_code_block(
    project_path: str,
    file_path: str,
    line: int,
    context_lines: int = 5
) -> dict:
    """Returns source lines around a finding's location from the live source file."""
    # Reads file_path relative to the registered project's source_path
    # Returns {"lines": [{"number": N, "content": "..."}], "file": "...", "line": N}
    # Must validate that file_path stays within the project sandbox (path traversal prevention)
```

### `get_file_lines`
Returns a specific range of lines from a source file.

```python
@mcp.tool()
async def get_file_lines(
    project_path: str,
    file_path: str,
    start_line: int,
    end_line: int
) -> dict:
    """Returns a specific line range from a source file."""
    # Safety: validate file_path is within project source root
    # Limit: end_line - start_line <= 100 to prevent large reads
```

---

## New Tool Group 3 (P0): Secret & Credential Detection

**Why P0:** `.secrets` file with AWS key, GitHub token, and DB password was completely missed. This is a critical security gap.

**Tools to implement:**

### `scan_secrets`
Triggers a targeted secret scan against the project (runs only trufflehog/secretscrub, not a full audit). Returns found secrets grouped by file.

```python
@mcp.tool()
async def scan_secrets(input: ProjectInput) -> dict:
    """Runs a targeted secret/credential scan and returns findings without triggering a full audit."""
```

**Note:** Requires trufflehog to be installed (covered in Group A plan). If trufflehog is not available, return `{"error": "Secret scanner not installed. Install trufflehog to enable this tool."}`.

### `list_credential_patterns`
Returns the configured credential detection patterns currently active.

```python
@mcp.tool()
async def list_credential_patterns(input: ProjectInput) -> dict:
    """Lists the credential and secret patterns currently configured for detection."""
```

---

## New Tool Group 4 (P1): Git & Commit Tracking

**Why P1:** After Group A Fix 4 (git commit stored in SQLite), trend data will have real commit hashes. These tools expose commit-level analysis.

**Tools to implement:**

### `get_commit_diff`
Compares findings between two specific git commits (uses `diff_runs` internally but accepts commit hashes instead of run IDs).

```python
@mcp.tool()
async def get_commit_diff(
    project_path: str,
    commit_a: str,
    commit_b: str
) -> dict:
    """Returns new and resolved findings between two git commits."""
    # Look up run_ids for the two commits from the SQLite runs table
    # Then delegate to the existing diff_runs logic
```

### `blame_finding`
Returns the git blame context for a finding's file and line — who last modified that line and when.

```python
@mcp.tool()
async def blame_finding(input: FindingHashInput) -> dict:
    """Returns git blame information for the file and line of a specific finding."""
    # Uses git blame on finding.file_path at finding.line
    # Requires git to be available on PATH
```

### `get_branch_findings`
Returns findings that are present only on the current branch (not on `main`/`master`).

```python
@mcp.tool()
async def get_branch_findings(input: ProjectInput) -> dict:
    """Returns findings introduced on the current branch compared to main."""
```

---

## New Tool Group 5 (P1): Working Sub-Score Engine

**Why P1:** After Group A Fix 3 (sub-scores computed from complete data), `security` and `quality` scores will be non-zero. These tools expose the breakdown in more detail.

**Tools to implement:**

### `get_score_breakdown`
Returns a detailed score breakdown by category and severity for the latest run.

```python
@mcp.tool()
async def get_score_breakdown(input: ProjectInput) -> dict:
    """Returns the detailed score breakdown by category (SECURITY, QUALITY, ARCHITECTURE) and severity."""
    # Reads from SQLite findings table, groups by category + severity, returns counts and score impact
```

### `get_category_trend`
Returns the security and quality sub-score trend across the last N runs.

```python
@mcp.tool()
async def get_category_trend(input: ProjectInput, last_n_runs: int = 10) -> dict:
    """Returns historical security and quality sub-score trends."""
    # Reads score_security, score_quality from SQLite runs table across last N runs
```

---

## New Tool Group 6 (P1): Audit Log MCP Access

**Why P1:** When 8 of 10 scanners produce no output, there is currently no way to determine via MCP whether they errored, timed out, or simply found nothing. Audit logs exist on disk but are inaccessible through the server.

**Tools to implement:**

### `get_job_log`
Returns the audit log for a specific job (or the latest job).

```python
@mcp.tool()
async def get_job_log(input: ProjectInput, run_id: Optional[str] = None, tail: int = 100) -> dict:
    """Returns the last N lines of the audit log for the specified (or latest) job."""
    # Log path: ~/.nexus_audit/projects/{project_id}/jobs/{job_id}/audit.log
    # Sandbox: validate path stays within project sandbox
```

### `get_scanner_errors`
Returns scanner-level error or timeout events from the latest job log.

```python
@mcp.tool()
async def get_scanner_errors(input: ProjectInput) -> dict:
    """Returns scanner error and timeout events from the latest audit job log."""
    # Parses audit.log for lines indicating scanner failure, timeout, or not-found
    # Returns {"errors": [{"scanner": "bandit", "event": "not_found", "message": "..."}]}
```

---

## New Tool Group 7 (P2): Finding Suppression Management

**Note:** Check with integration agent first — they may include suppression in F-09. If F-09 handles suppression via fix queue status updates, these tools may be redundant or should be scoped to a read-only view of existing suppressions.

**Tools to implement:**

### `suppress_finding`
Marks a finding as suppressed with a mandatory documented reason and optional review date.

```python
@mcp.tool()
async def suppress_finding(
    project_path: str,
    finding_hash: str,
    reason: str,      # min 15 chars, enforced
    review_date: Optional[str] = None  # ISO date for scheduled re-review
) -> dict:
    """Suppresses a known false positive with a documented reason."""
```

### `list_suppressions`
Returns all currently suppressed findings with their reasons and review dates.

```python
@mcp.tool()
async def list_suppressions(input: ProjectInput) -> dict:
    """Lists all suppressed findings for a project."""
```

---

## New Tool Group 8 (P3): API Contract Validation

Lowest priority. No overlap with integration agent. Implement only after Groups A, B, C1-6 are complete.

**Tools:** `validate_api_contracts`, `diff_openapi_specs`

These require OpenAPI/contract schema files to be present in the project. The implementation is project-configuration-dependent and should not be designed until a specific project with API contracts is available for testing. Defer detailed spec to that time.

---

## Implementation order for the agent

1. Group C1 (Audit Health Check) — implement `get_job_manifest` skeleton first, then update the orchestrator to emit `scanner_results`, then implement `verify_fresh_run`
2. Group C2 (Code Intelligence) — `get_snippet_by_hash` first (simpler, uses SQLite), then `get_code_block` and `get_file_lines` (file reads with path validation)
3. Group C3 (Secret Detection) — requires trufflehog installed; implement the tool shell first, add graceful error if binary missing
4. Group C4 (Git Tracking) — after Group A Fix 4 (git_commit in SQLite) is verified
5. Group C5 (Sub-Score Engine) — after Group A Fix 3 (sub-scores non-zero) is verified
6. Group C6 (Audit Log MCP Access) — straightforward file reads, no dependencies
7. Group C7 (Finding Suppression) — coordinate with integration agent first
8. Group C8 (API Contract Validation) — defer until project with contracts available

---

## Verification checklist (auditor confirms after Group C is implemented)

- [ ] `get_job_manifest` returns a `scanner_results` list with status per scanner (requires orchestrator update)
- [ ] `verify_fresh_run` returns `{"fresh": true, "age_seconds": <realistic_value>}` immediately after a run
- [ ] `get_snippet_by_hash` returns non-null `snippet` for a bandit finding (requires Group A + Group B Fix B5)
- [ ] `get_code_block` returns source lines for a finding's location; rejects paths outside project root
- [ ] `get_file_lines` with `end_line - start_line > 100` returns an error
- [ ] `scan_secrets` returns `{"error": "..."}` if trufflehog not installed; returns findings if installed
- [ ] `get_job_log` returns the last N lines of `audit.log` for the latest job
- [ ] `get_scanner_errors` returns a list of scanner error events when bandit or semgrep fails
- [ ] `get_score_breakdown` returns non-zero counts after scanners run
- [ ] `pytest tests/ -q` — all tests pass after each tool group is added
