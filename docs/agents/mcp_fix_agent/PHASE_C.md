# Phase C — New MCP Tool Groups
**Start Phase C only after Phase A and Phase B are complete and verified by the Lead Auditor.**
**Phase C requires research before implementation. You must follow the procedure below.**

---

## Procedure for each tool group

You must do this for **each tool group**, one at a time, in the priority order listed:

1. **Write a `WHAT.md`** in `docs/agents/mcp_fix_agent/phase_c/C{N}_what.md`
   describing exactly what the tool group does, why it's needed, and what data
   sources it reads from. Be specific — implementation-level detail.

2. **Run the LLM council** (see `Skills/llm-council.md` in the Obsidian vault
   `nexus_audit_v3`) with at least 3 expert perspectives before implementing.
   Questions to ask: API design, error handling, security (path traversal, injection),
   interaction with existing tools.

3. **Write a council verdict** in `docs/agents/mcp_fix_agent/phase_c/C{N}_verdict.md`
   summarising the council's recommendation and any implementation constraints.

4. **Implement** only after steps 1–3 are done.

5. **Update `STATUS.md`** and commit before moving to the next tool group.

---

## Tool groups in priority order

### C1 (P0): Audit Engine Health Check

Tools: `get_job_manifest`, `verify_fresh_run`

`get_job_manifest` returns a structured manifest of the latest audit job:
file count, per-scanner status (ran / skipped / errored), per-scanner duration,
start/end timestamps, job ID.

`verify_fresh_run` returns `{"fresh": true/false, "run_id": "...", "age_seconds": N}` —
confirms the latest run completed within a configurable window and has non-zero duration.

**Key implementation note:** `get_job_manifest` needs per-scanner status data. This
currently does not exist in `audit_data_complete.json`. Research whether the orchestrator
already logs per-scanner outcomes, and if not, what change to `orchestrator.py` is needed
to emit it. This is the main research question for C1.

**Security:** No path traversal risk — reads from `~/.nexus_audit/projects/{id}/jobs/`.

---

### C2 (P0): Code Intelligence

Tools: `get_snippet_by_hash`, `get_code_block`, `get_file_lines`

`get_snippet_by_hash` — returns the stored snippet for a finding fingerprint (reads
from the `snippet` column added in Phase B Fix B5).

`get_code_block` — returns N lines of source code around a file/line reference by
reading the live source file on disk. **Security is the main research question:**
how do you sandbox the file read to the registered project root? What happens if
the `file` field in a finding points outside the project directory?

`get_file_lines` — returns a specific line range. Hard limit: `end_line - start_line <= 100`.

---

### C3 (P0): Secret & Credential Detection

Tools: `scan_secrets`, `list_credential_patterns`

`scan_secrets` triggers a targeted scan (trufflehog / secretscrub only, not a full
audit). Returns found secrets grouped by file. Must return a clear error if trufflehog
is not installed.

**Research question:** Does triggering a partial scan reuse the existing orchestrator
scan phase, or does it need its own lightweight runner? What does the output format
of trufflehog look like and how does it map to the `Finding` dataclass?

---

### C4 (P1): Git & Commit Tracking

Tools: `get_commit_diff`, `blame_finding`, `get_branch_findings`

Depends on Phase A Fix A3 (git_commit stored in SQLite runs table) being verified
before this is useful.

`get_commit_diff` — compares findings between two git commits by looking up the
corresponding run IDs in SQLite and delegating to the existing `diff_runs` logic.

`blame_finding` — runs `git blame` on the finding's file and line. **Research
question:** How do you handle findings where `file` is a relative path — what is
the correct working directory for the `git blame` call?

`get_branch_findings` — findings present on the current branch but not on `main`.

---

### C5 (P1): Working Sub-Score Engine

Tools: `get_score_breakdown`, `get_category_trend`

Depends on Phase A Fix A2 (sub-scores non-zero) being verified first.

`get_score_breakdown` — detailed per-category, per-severity breakdown for the
latest run (queries the `findings` SQLite table).

`get_category_trend` — historical `score_security` and `score_quality` across
the last N runs (queries the `runs` SQLite table).

---

### C6 (P1): Audit Log MCP Access

Tools: `get_job_log`, `get_scanner_errors`

`get_job_log` — returns the last N lines of `audit.log` for the latest (or a
specified) job. Log path: `~/.nexus_audit/projects/{id}/jobs/{job_id}/audit.log`.

`get_scanner_errors` — parses the log for scanner failure/timeout/not-found events.
**Research question:** What is the log format for scanner errors? Read
`core/infra/audit_logger.py` before writing `WHAT.md` for this one.

---

### C7 (P2): Finding Suppression Management

Tools: `suppress_finding`, `list_suppressions`, `get_suppression_reason`

**Check with the integration agent first** — F-09 (Fix Queue API) may include a
`suppressed` status in `PATCH /api/fix-queue/{id}`. If it does, these tools may
be redundant or should be scoped to read-only views. Leave a message in
`INTEGRATION_JOURNAL.md` and wait for a response before writing `WHAT.md` for C7.

---

### C8 (P3): API Contract Validation

Tools: `validate_api_contracts`, `diff_openapi_specs`

Lowest priority. Only implement once C1–C6 are done and NexusTestBed has
OpenAPI contract files to validate against. If no contract files exist yet,
defer entirely and note in `STATUS.md`.

---

## Files you will likely touch in Phase C

- `core/mcp/tools/` — new tool files (one per group, or grouped by theme)
- `core/mcp/server.py` — register new tools
- `core/infra/audit_index.py` — new queries if needed
- `orchestrator.py` — only if C1 requires a metadata change to emit per-scanner results

**Do not touch** anything in the integration agent's file touch map (listed in `AGENT_BRIEF.md`).
