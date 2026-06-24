> **⚠ SUPERSEDED** — this draft did the reconciliation work, but
> `MCP_SPECIFICATION.md` (same folder) is the full, self-contained result
> and is now authoritative. This file is kept as the intermediate step in
> the record, not as something to implement from. Everything below is
> unchanged from when it was written.

# Nexus Audit V3 — MCP Server Specification (Current)

**Status:** Authoritative. Supersedes `spec /nexus_audit_v3_mcp_specification.md`
and `specs/Nexus Audit v3 MCP Expansion.md` for everything described below.

**Why this document exists:** Those two files were written independently,
at different times, arguing for two incompatible philosophies — one
strictly read-only, one allowing configuration writes — and were never
reconciled against each other. Session 2 implementation work followed the
second one without revisiting the first one's reasoning. This document is
the result of actually reconciling them: it keeps what both got right,
drops what the evidence (a live MCP test session against a real project)
showed didn't matter, and adds the one mechanism that was missing from
both — a way to tell "this configuration change makes the audit stricter"
apart from "this configuration change makes the audit easier to pass."

The two superseded documents are kept for historical record. Do not
implement from them going forward.

---

## 1. What Changed, and Why

### 1.1 The original position (read-only)

The first MCP specification established a hard boundary: the server only
ever reads. The reasoning was the Confused Deputy pattern — an agent
tricked by prompt injection or its own hallucination into taking a harmful
action through a tool that has more local permission than the agent
itself should be trusted with directly.

### 1.2 The expansion (config-write capability)

A later strategy document argued this boundary was overly conservative:
toggling a JSON config value isn't Remote Code Execution, and standard
industry practice (the official Anthropic filesystem MCP server, for
example) already treats sandboxed config/file writes as acceptable
"operational risk," distinct from "system risk" like arbitrary shell
execution or path traversal. Five tools were built on this reasoning:
`enable_scanners`, `disable_scanners`, `set_scanner_config`,
`set_project_config`, `generate_audit_report`. Mandatory reasoning fields
(minimum 15 characters) and an append-only audit log were added as the
mitigation for the risk the document itself identified — an agent that
can't fix a flagged vulnerability quietly disabling the scanner that
flagged it instead.

### 1.3 What a live test session actually showed

These tools were exercised against a real registered project through
Claude Desktop. Every one of them worked exactly as designed — reasoning
enforcement correctly rejected a too-short justification, scanner toggles
applied, config patches applied, reports wrote to disk inside the
sandbox. Then the agent was asked directly: given everything this tool
just told you, could you confidently maintain this project's quality
using it. The answer was no — and none of the seven reasons given were
about wanting more configuration control. They were: a fix queue that
returns empty despite confirmed open findings, security/quality sub-scores
hardcoded to zero on every run, an audit that completes in 0ms, finding
snippets that are always null, dead git commit tracking, no cross-service
visibility, and seven duplicate registrations of the same project under
different IDs.

The capability that was built specifically to make the agent more
effective was not what limited the agent's effectiveness. The audit
engine's read-side reliability was. That is the central finding this
document is built on.

### 1.4 The resolution

Configuration-write capability is not removed. The argument for it is
real: an agent that has just read and reasoned about a specific codebase
plausibly understands its boundaries — which modules are intentional thin
wrappers, which services don't need a given scanner — better than a
static, human-authored config file can. That asymmetry is worth keeping.

But every configuration action has a direction relative to audit rigor.
Some actions can only make the audit *stricter* (enabling a scanner,
raising a strictness level, lowering a findings threshold). Some can only
make it *easier to pass* (disabling a scanner, lowering strictness,
raising a threshold). There is no plausible good-faith reason for an
agent to loosen its own audit on its own authority. There is an obvious
bad-faith — or simply lazy — reason for it to do exactly that.

**The rule going forward: tightening actions apply immediately. Loosening
actions are written to a pending-approval queue and do not take effect
until a human approves them from the CLI.** Neither side of the original
disagreement gets to keep an unqualified win. The capability stays; the
direction that can do harm gets a human in the loop before it's real,
not just a log entry to discover after the fact.

---

## 2. Tool Registry — Current State

15 tools, in four groups. Groups 1–3 are unchanged from the original
specification and the test session confirmed they behave as designed
(independent of whatever bugs exist in the audit engine underneath them —
see Section 4). Group 4 is where this document changes behavior.

### Group 1 — Discovery (read-only, unchanged)
- `get_server_info`
- `list_projects` *(not in the original 9-tool spec; added during
  implementation, confirmed working, kept as-is — a multi-project server
  needs a way to enumerate what's registered)*

### Group 2 — Audit Execution (read-only at the tool-call level; the one
side effect, a new run, is the server's designed exception, same as the
original spec)
- `run_project_audit`
- `get_latest_audit_summary`

### Group 3 — Findings & Analytics (read-only, unchanged)
- `get_finding_detail`
- `list_findings`
- `get_file_context`
- `get_fix_queue`
- `get_trend`
- `diff_runs`

### Group 4 — Configuration (write-capable, direction-gated — see Section 3)
- `enable_scanners` — **tightening, always.** Applies immediately.
- `disable_scanners` — **loosening, always.** Goes to the pending queue.
- `set_scanner_config` — **direction depends on the value.** See 3.2.
- `set_project_config` — **direction depends on the key.** See 3.3.
- `generate_audit_report` — **neutral.** Writing a report doesn't change
  audit rigor. Applies immediately, unchanged from current behavior,
  including the existing path-sandboxing.

`project:register` and `project:delete` remain CLI-only, human-only, with
no MCP equivalent. This was correct in both prior documents and isn't
being revisited here.

---

## 3. Direction Gating — The Mechanism

### 3.1 `enable_scanners` / `disable_scanners`

No ambiguity — a scanner is either on or off, and turning one on can only
ever add coverage. `enable_scanners` keeps its current immediate-apply
behavior unchanged. `disable_scanners` changes: instead of calling
`patch_project_settings` directly, it writes a pending entry (see 3.4)
and returns a message telling the agent the change requires human
approval before it takes effect.

### 3.2 `set_scanner_config` (strictness)

Requires a defined ordering of strictness levels, e.g.
`strict > standard > lenient`. Compare the requested level against the
scanner's current level:
- Requested level is **stricter** than current → tightening → apply
  immediately.
- Requested level is **looser** than current → loosening → pending queue.
- Same level → no-op, return success without logging a change.

### 3.3 `set_project_config`

This tool currently accepts an open `config_patch` dict with no key
allowlist — meaning an agent could in principle patch any field on
`ProjectSettings`, including ones with no relationship to audit rigor at
all. That gap gets closed here, independent of direction gating: **the
tool must validate every key in `config_patch` against an explicit
allowlist of audit-relevant settings.** Any key not on the allowlist is
rejected outright — not queued, rejected — since an unknown key has no
defined direction and therefore no safe default behavior.

For allowlisted keys, direction is evaluated per key:
- `max_high_findings`, `max_critical_findings`, and similar thresholds:
  **lowering** the number is tightening (fewer findings tolerated before
  failing) → immediate. **Raising** the number is loosening → pending.
- `retention.max_jobs` and similar: this does not affect audit rigor.
  Classify as neutral → immediate, same as `generate_audit_report`.
- Any other key proposed for the allowlist must be classified
  explicitly, in writing, in this document, before being added. No key
  is added to the allowlist without a stated direction rule.

### 3.4 The Pending Queue

A new file, `~/.nexus_audit/projects/<project_id>/pending_changes.json` —
same pattern and location precedent as `.nexus_fix_queue.json`, a flat
JSON array:

```json
[
  {
    "id": "a1b2c3d4",
    "tool": "disable_scanners",
    "params": {"scanner_name": "bandit"},
    "reasoning": "This service has no Python execution paths; bandit findings are false positives.",
    "requested_at": "2026-06-23T10:00:00Z",
    "status": "pending"
  }
]
```

When a loosening action is requested, the MCP tool:
1. Validates the input exactly as it does today (schema, reasoning length).
2. Writes the entry above with `status: "pending"`.
3. Returns to the agent: *"This change loosens audit strictness and
   requires human approval. Pending ID: `a1b2c3d4`. Run
   `mcp:approve a1b2c3d4` from the CLI to apply it, or it will not take
   effect."* The agent's reasoning is preserved and shown to the human at
   approval time — the existing audit-log write still happens, in
   addition to the queue entry, not instead of it.

### 3.5 New CLI Commands

- `mcp:pending` — list all entries with `status: "pending"`, including
  the tool, params, and reasoning, for the active project.
- `mcp:approve <id>` — applies the queued change using the exact same
  underlying `patch_project_settings`/scanner-toggle call the MCP tool
  would have made directly, then sets `status: "approved"`.
- `mcp:reject <id>` — sets `status: "rejected"`. The change never applies.

These are ordinary CLI commands, OPERATOR privilege, no different in
structure from any other handler in this codebase — they read the queue
file, render it or mutate an entry's status, nothing more.

---

## 4. Explicitly Out of Scope Here

The following are real, confirmed problems from the test session. They
are not addressed by this document, on purpose — per the agreed sequence,
the architecture question (this document) is settled first, then these
get fixed against a stable target rather than a moving one:

- `security`/`quality` sub-scores hardcoded to `0.0` on every run
- `run_project_audit` completing in `duration_ms: 0` — needs confirmation
  of whether a real scan is happening at all
- `get_fix_queue` returning empty despite confirmed open findings
- Finding `snippet` fields always `null`
- `git_commit` always `"?"` in trend/summary output
- Seven duplicate registrations of the same project path under different
  UUIDs

None of these are touched by anything in Sections 2–3. Fixing them does
not require revisiting this document, and this document does not depend
on them being fixed first.

---

## 5. What Stays Exactly As It Is

- Groups 1–3 (10 tools): no behavior change, no schema change.
- The Pydantic schema validation and mandatory-reasoning pattern already
  built for Group 4: kept, unchanged, for every tool in that group.
- `generate_audit_report`'s existing path-sandboxing: kept, unchanged.
- The append-only audit log at `~/.nexus_audit/mcp_action_log.txt`: kept.
  The pending queue is additive to it, not a replacement.
- `project:register` / `project:delete`: CLI-only, unchanged.

---

*This document lives on `feature/mcp-server-sqlite-index`. It is not
merged into `main` and will not be by anyone other than the project
owner, after review.*
