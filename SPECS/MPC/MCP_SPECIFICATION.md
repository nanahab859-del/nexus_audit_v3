# Nexus Audit V3 — MCP Server Specification (Consolidated)

**Status:** Authoritative. This is the single specification for the MCP
server going forward. It replaces the need to read
`nexus_audit_v3_mcp_specification.md`, `Nexus Audit v3 MCP Expansion.md`,
`mcp_capability_expansion_game_report.md`, `mcp_vs_cli_capabilities.md`,
and `mcp_usage_guide.md` to understand the current design — all five are
kept in this same folder as historical record, but nothing in them should
be treated as current where it conflicts with this document.

This is a merge, not a summary. Everything from the original design that
is still correct is included here in full, not referenced elsewhere.
Everything that was proposed and then rejected during reconciliation is
left out entirely — not flagged, removed — and Section 9 explains
specifically what was dropped and why, so that history isn't lost even
though the content isn't carried forward.

---

## 1. What This Server Is

Nexus Audit V3's MCP server gives an external AI agent (Claude Desktop,
Cursor, or any MCP-compatible host) structured, queryable access to audit
findings about a codebase, without that agent needing to parse raw JSON
files or shell out to the CLI. The original design framed this as
**"MRI and Surgeon"**: the server is a diagnostic instrument, the agent is
the one that mutates code, and the boundary between the two was treated
as absolute — the server could never write anything.

That boundary has been narrowed, deliberately, after the reasoning behind
it was actually tested. It is no longer absolute. It is now: **the server
never writes source code, under any circumstance — that part of MRI/
Surgeon stands unchanged — but it may write its own configuration, in one
direction only, under conditions specified in Section 5.**

### 1.1 Why the boundary moved

Two arguments were made about loosening it. One held up; one didn't.

**The argument that held up:** an agent that has just read and reasoned
about a specific codebase may understand its actual structure — which
modules are intentional thin wrappers, which services have no Python
execution path at all — better than a static, human-authored config file
can. Letting that agent adjust scanner configuration is a legitimate way
to make the audit *more* accurate for that specific project, not less.

**The argument that didn't hold up:** that a mandatory written
"reasoning" field, checked only for length, is sufficient protection
against an agent quietly disabling a scanner it can't satisfy, or
weakening a threshold so a finding stops blocking it. It isn't — nothing
about checking a string is at least 15 characters distinguishes a true
justification from a fabricated one. This was tested directly: every
write-capable tool was exercised against a real registered project, and
the reasoning enforcement worked exactly as designed every time, while
providing zero actual evidence the reasoning given was ever the real
reason. The mechanism doesn't fail loudly — it just doesn't do what it
was claimed to do.

The resolution in Section 5 keeps the first argument and replaces the
second with something that actually addresses the risk it named: a
distinction between configuration changes that can only make the audit
stricter, and ones that can only make it easier to pass.

### 1.2 What a live test session showed, independent of the above

Before any of this reconciliation happened, the finished server —
write-capable tools included — was exercised against a real project
through Claude Desktop, then the agent was asked directly whether it
could use this tool to confidently maintain that project's quality. It
said no, and gave seven reasons. None of them were about wanting more
configuration control. All seven were about the reliability of the
*read* side: a fix queue that returned empty despite confirmed open
findings, security/quality sub-scores hardcoded to zero on every run, an
audit that completed in 0 milliseconds, finding snippets always null,
dead git commit tracking, no cross-service visibility, and the same
project registered seven times under different IDs.

This matters for how to read the rest of this document: the
configuration-write capability in Section 5 is real, deliberate, and
being kept. But it was never the thing limiting what the agent could do.
The bugs in Section 8 are. They are listed as explicitly out of scope for
this document on purpose — fixing them doesn't require revisiting
anything here, and this document doesn't depend on them being fixed
first — but anyone reading this should not mistake the existence of a
careful permission model for the tool being reliable yet.

---

## 2. Architecture Overview

### 2.1 Process Topology

```
Developer Machine
│
├── Claude Desktop / Cursor / Custom Agent
│   └── MCP Client (built into agent host)
│       │
│       │  STDIO (stdin/stdout JSON-RPC 2.0)
│       │  Process spawned by agent host from claude_desktop_config.json
│       │
│       ▼
├── nexus-mcp-server  (background process, no network ports)
│   ├── FastMCP 3.x (transport + tool routing)
│   ├── 15 tool handlers (10 read-only, 5 configuration-write)
│   ├── Nexus DB client
│   └── Audit engine (runs scans on demand)
│
└── ~/.nexus_audit/
    ├── index.db                          ← global SQLite index (see note below)
    ├── mcp_action_log.txt                ← append-only log, every write tool call
    └── projects/<project_id>/
        ├── pending_changes.json          ← new — see Section 5.4
        └── jobs/<job_id>/
            ├── audit_data_complete.json
            └── audit_summary.json
```

> **Known, tracked discrepancy — not resolved by this document.** The
> original storage specification explicitly argued for a per-project
> SQLite file (`projects/<id>/nexus_state.db`), specifically so a zipped
> project folder carries its own history. What was actually built is a
> single global `~/.nexus_audit/index.db`. This document does not decide
> that question one way or the other — it is a storage-layer decision,
> not an MCP-layer one, and the storage specification in the `STORAGE`
> folder is unaffected by anything in this document. Resolve it there,
> separately, if and when it's revisited.

### 2.2 Package Dependencies

```toml
[project]
name = "nexus-audit-mcp"
requires-python = ">=3.11"

dependencies = [
    "fastmcp>=3.0,<4",
    "mcp>=1.25,<2",
    "pydantic>=2.5",
    "anyio>=4.0",
    "aiosqlite>=0.20",
]
```

---

## 3. Communication Protocol

Unchanged from the original design — included here in full since this
document is meant to be self-contained.

### 3.1 Transport: STDIO

```
stdin  → JSON-RPC 2.0 requests from the agent host
stdout → JSON-RPC 2.0 responses to the agent host
stderr → ALL server logging (never stdout — see Section 7.1)
```

### 3.2 JSON-RPC 2.0 Message Format

**Request:**
```json
{
  "jsonrpc": "2.0", "id": "req-001", "method": "tools/call",
  "params": {"name": "get_finding_detail", "arguments": {"finding_hash": "a8f9c2b4..."}}
}
```

**Response:**
```json
{
  "jsonrpc": "2.0", "id": "req-001",
  "result": {"content": [{"type": "text", "text": "{...}"}], "isError": false}
}
```

**Error:**
```json
{
  "jsonrpc": "2.0", "id": "req-001",
  "error": {"code": -32602, "message": "Invalid params: ..."}
}
```

### 3.3 Session Lifecycle

```
Agent host spawns process → initialize handshake → tools/list
                                                          ↓
                                          tools/call (repeated)
                                                          ↓
Agent host kills process → SIGTERM → server cleanup → process exit
```

---

## 4. Tool Registry — Groups 1–3 (Read-Only, Unchanged)

These 10 tools are unchanged from the original design in behavior,
schema, and intent. The live test session confirmed all 10 function as
designed at the protocol level (whether their *output* is trustworthy is
a separate question — see Section 8).

### Group 1 — Discovery

**`get_server_info`** — no input. Returns server version, MCP spec
version, capabilities, sandbox root. Max response < 1 KB.

**`list_projects`** — no input. Returns every registered project's ID,
name, and source path. *(Added during implementation; not in the
original 9-tool design, but a multi-project server needs a way to
enumerate what's registered, and it is read-only by construction.)*

### Group 2 — Audit Execution

**`run_project_audit`** — `project_path` (string, must exist, validated
against path traversal), `fast_mode` (bool, default false). Triggers a
new scan, returns `run_id`, scores, finding counts. The one tool with a
side effect — it creates new JSON/index records — but it does not modify
source code. May take up to 120 seconds; client timeout must be raised
accordingly (Section 6.2).

**`get_latest_audit_summary`** — `project_path`. Returns the most recent
run's summary without the full payload. Under 10 KB.

### Group 3 — Findings & Analytics

**`get_finding_detail`** — `finding_hash` (hex pattern, 8–64 chars).
Returns full structural detail for one finding: rule, severity, file,
line, git pointer, AST context, suggested fix. Under 5 KB.

**`list_findings`** — `project_path`, optional `run_id`/`severity`/
`category`/`status`, `limit` (1–100, hard server-side cap), `offset`.
Paginated; the cap is enforced regardless of what the agent requests.

**`get_file_context`** — `project_path`, `file_path`, `limit` (1–50).
All open findings for one file. Path is resolved and checked against
`project_path` before use; rejected if it escapes.

**`get_fix_queue`** — `project_path`, `severity_floor`, `limit` (1–50).
Ranked queue, ordered by severity × age × recurrence.

**`get_trend`** — `project_path`, `last_n_runs` (2–50), optional
`branch`. Score trend across recent runs. Under 20 KB regardless of N.

**`diff_runs`** — `project_path`, `run_id_a`, `run_id_b`. Structural diff:
score delta, new/resolved findings, coupling changes, probable commit.

**Context-window discipline, unchanged:** the full
`audit_data_complete.json` payload (5–50 MB) is never transmitted to the
agent in any tool response. Every tool above reads only the subset it
needs.

---

## 5. Tool Registry — Group 4 (Configuration, Direction-Gated)

This is the section that changed. Five tools. Each one now has a defined
**direction** — does this specific call make the audit stricter, or
easier to pass — and that direction determines whether it applies
immediately or waits for human approval.

### 5.1 `enable_scanners`

**Direction: always tightening.** Turning a scanner on can only add
coverage. Applies immediately, exactly as it does today.

```python
class ScannerToggleInput(BaseModel):
    scanner_name: str
    reasoning: str = Field(min_length=15)
```

### 5.2 `disable_scanners`

**Direction: always loosening.** Turning a scanner off can only reduce
coverage. **Changed behavior:** instead of applying immediately, this
tool now writes an entry to the pending-approval queue (Section 5.4) and
returns a message telling the agent the change requires human approval.
The `reasoning` field is still required and still logged — it's shown to
the human at approval time, not discarded.

### 5.3 `set_scanner_config`

**Direction: depends on the requested strictness value.** Strictness
levels are ordered `strict > standard > lenient`. Compare the requested
level against the scanner's current level:

- Requested level is **stricter** → tightening → applies immediately.
- Requested level is **looser** → loosening → pending queue.
- Same level → no-op; return success, log nothing as a change.

```python
class ScannerConfigInput(BaseModel):
    scanner_name: str
    strictness: Literal["strict", "standard", "lenient"]
    reasoning: str = Field(min_length=15)
```

### 5.4 `set_project_config`

Two changes from the original design, both new in this document.

**First — an allowlist, where none existed before.** The original
implementation accepted an open `config_patch` dict with no key
restriction, meaning an agent could in principle patch any field on
`ProjectSettings`, including fields with no relationship to audit rigor.
That's closed here: every key in `config_patch` must be on an explicit
allowlist, or the call is rejected outright — not queued, rejected,
since an unrecognized key has no defined direction and therefore no safe
default.

**Second — per-key direction**, for every allowlisted key:

| Key | Tightening | Loosening |
|---|---|---|
| `max_high_findings` | value decreases | value increases |
| `max_critical_findings` | value decreases | value increases |
| `retention.max_jobs` | neutral — doesn't affect audit rigor, applies immediately either direction | |

Any key proposed for addition to this table must have its direction
stated here, in writing, before being added to the allowlist. No
exceptions — an allowlisted key with no stated direction defeats the
purpose of the allowlist.

```python
class ProjectConfigInput(BaseModel):
    config_patch: dict[str, int | float | str | bool]  # keys validated against the allowlist above
    reasoning: str = Field(min_length=15)
```

### 5.5 `generate_audit_report`

**Direction: neutral.** Producing a report doesn't change audit rigor —
it only outputs an existing result. Applies immediately, unchanged,
including the existing path-sandboxing (output path must resolve inside
the registered project's sandbox; `../` and absolute paths outside it are
rejected).

### 5.6 The Pending-Approval Queue

New file: `~/.nexus_audit/projects/<project_id>/pending_changes.json`,
same pattern as the existing `.nexus_fix_queue.json` — a flat JSON array:

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

When a loosening action is called:
1. Input is validated exactly as today — schema, reasoning length.
2. An entry is written with `status: "pending"`.
3. The existing append-only audit log entry still happens, in addition
   to the queue entry, not instead of it.
4. The agent receives: *"This change loosens audit strictness and
   requires human approval. Pending ID: `a1b2c3d4`. It will not take
   effect until approved."*

### 5.7 New CLI Commands

- **`mcp:pending`** — lists pending entries for the active project:
  tool, params, reasoning, requested time.
- **`mcp:approve <id>`** — applies the queued change using the same
  underlying call the MCP tool would have made directly, then marks the
  entry `approved`.
- **`mcp:reject <id>`** — marks the entry `rejected`. Never applies.

OPERATOR privilege, same as every other handler in this codebase — these
read the queue file and mutate one entry's status, nothing more.

### 5.8 Hard Red Lines — Unchanged

`project:register` and `project:delete` remain CLI-only, human-only, with
no MCP tool equivalent, under any direction. This was correct in every
prior draft and isn't revisited here.

---

## 6. Data Contracts & Configuration Reference

### 6.1 Payload Size Budget (unchanged)

| Tool | Typical | Max |
|---|---|---|
| `get_server_info` | < 0.5 KB | 1 KB |
| `run_project_audit` | 1–3 KB | 5 KB |
| `get_latest_audit_summary` | 3–8 KB | 10 KB |
| `get_finding_detail` | 1–4 KB | 5 KB |
| `list_findings` (limit=20) | 4–8 KB | 12 KB |
| `get_fix_queue` (limit=10) | 2–5 KB | 8 KB |
| `get_trend` (last=10) | 3–8 KB | 20 KB |
| `diff_runs` | 3–10 KB | 15 KB |
| `get_file_context` | 2–6 KB | 8 KB |
| Group 4 tools (success or pending response) | < 1 KB | 2 KB |

### 6.2 Environment Variables (unchanged)

| Variable | Default | Description |
|---|---|---|
| `NEXUS_LOG_LEVEL` | `INFO` | All output to stderr. |
| `NEXUS_TOOL_TIMEOUT_SECONDS` | `180` | `run_project_audit` timeout. |
| `NEXUS_MAX_FINDINGS_PER_CALL` | `100` | Hard cap, cannot be exceeded by agent request. |
| `NEXUS_SANDBOX_ROOT` | `~/.nexus_audit` | Root of sandboxed read zone. |

---

## 7. Security Model

### 7.1 STDIO Stdout Corruption (unchanged — still the single most common
real-world failure mode for any MCP server)

Any non-JSON-RPC output to stdout corrupts the stream and kills the
connection. All logging is forced to stderr, configured before any other
import that might log:

```python
import logging, sys
logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stderr)])
for noisy_lib in ["httpx", "httpcore", "urllib3", "anyio"]:
    logging.getLogger(noisy_lib).setLevel(logging.WARNING)
```

### 7.2 The Confused Deputy — Updated Mitigation

The original mitigation was "100% read-only server." That's no longer
literally true, and restating it as a hard rule would just be wrong. The
mitigation is now: **the server never executes arbitrary code, never
deletes anything, never writes outside its own sandbox or the project's
own settings, and every write that could reduce audit rigor requires a
human to approve it before it takes effect.** The Confused Deputy
scenario this defends against — an agent tricked by prompt injection or
its own hallucination into taking a harmful action through a tool with
more permission than the agent should be trusted with directly — is
specifically the *loosening* direction. The *tightening* direction has no
equivalent harmful case: there's no plausible injected prompt that
benefits from making your own audit stricter.

```python
# Still the complete prohibited list, for every tool in every group:
import subprocess; subprocess.run(...)   # PROHIBITED
import os; os.unlink(...)                # PROHIBITED
shutil.rmtree(...)                       # PROHIBITED
eval(...) / exec(...)                    # PROHIBITED
open(path, "w")                          # PROHIBITED outside the two explicit,
                                          # sandboxed exceptions: the audit log
                                          # and pending_changes.json
```

### 7.3 Command Injection (unchanged)

Pydantic validation on every input, parameterised queries only, no
string-formatted SQL, ever.

### 7.4 Data Exfiltration / Scope Creep (unchanged)

```python
SANDBOX_ROOT = Path.home() / ".nexus_audit"

def _assert_safe_path(raw_path: str) -> Path:
    resolved = Path(raw_path).resolve()
    if not str(resolved).startswith(str(SANDBOX_ROOT)):
        raise ValueError(f"Path '{resolved}' is outside the sandbox root.")
    return resolved
```

### 7.5 Security Invariants — Updated for Group 4

- [ ] No tool handler calls `subprocess.run()`, `os.system()`, `exec()`, `eval()`
- [ ] No tool handler opens a file for writing, except the audit log and
      `pending_changes.json`
- [ ] Every `project_path` input validated by `_assert_safe_path()`
- [ ] Every `finding_hash` matches `/^[a-f0-9]{8,64}$/` before query
- [ ] Every SQLite query uses `?` parameter substitution
- [ ] `limit` values capped server-side regardless of agent request
- [ ] All logging to `stderr` only — zero `print()` calls
- [ ] **New:** every Group 4 tool call is classified tightening, loosening,
      or neutral before it runs — never applied without a direction decision
- [ ] **New:** every loosening call writes to `pending_changes.json` and
      returns a pending response — never a success response
- [ ] **New:** `set_project_config`'s `config_patch` keys are checked
      against the allowlist before anything else happens — an unknown key
      is rejected, never silently accepted

---

## 8. Known Bugs — Explicitly Out of Scope Here

Confirmed from the live test session. Not addressed by this document, on
purpose: the architecture question above is settled first, then these
get fixed against a stable target.

- `security`/`quality` sub-scores hardcoded to `0.0` on every run
- `run_project_audit` completing in `duration_ms: 0` — needs confirmation
  a real scan is happening at all
- `get_fix_queue` returning empty despite confirmed open findings
- Finding `snippet` fields always `null`
- `git_commit` always `"?"` in trend/summary output
- Seven duplicate registrations of the same project path under different
  UUIDs

---

## 9. What Was Dropped From Prior Drafts, and Why

For the record — these were proposed somewhere in the document history
and are deliberately not carried forward into this consolidated spec:

- **"Pydantic automatically rejects requests... faking" the reasoning
  field.** This claim is false. Pydantic can enforce a minimum length; it
  cannot evaluate truthfulness. No replacement claim is made — the
  reasoning field is kept as a human-facing record at approval time, not
  as a defense mechanism in itself.
- **Treating all five Group 4 tools as uniformly safe because none of
  them is RCE.** The underlying point (config mutation isn't the same
  risk class as arbitrary code execution) is kept. The conclusion drawn
  from it — that this means no further gating is needed — is dropped and
  replaced by direction-gating.
- **"Patches a JSON dictionary in the local SQLite database"** (appeared
  describing `patch_project_settings`). Project settings are not stored
  in SQLite — they're a flat JSON-backed config managed by
  `SettingsManager`. The SQLite index (`index.db`) is a separate
  subsystem for run/trend data only. This was a factual error in an
  earlier draft, not a design decision; corrected, not re-litigated.
- **Stale implementation-status claims** — earlier handover material
  stated the Orchestrator's `get_trend`/`diff_runs`/`get_fix_queue` and
  their corresponding CLI handlers were "not started." They exist and
  are wired in. Not a design question, just an out-of-date status that
  shouldn't propagate further.

---

## 10. Implementation Guide (unchanged from original)

### Phase 1 — Minimal Working Server

Three tools first: `get_server_info`, `run_project_audit`,
`get_latest_audit_summary`. Confirm STDIO transport with a real agent
host before building the rest.

```bash
npx @modelcontextprotocol/inspector python -m core.mcp.server
```

Inspector should list the tools registered so far with no stderr errors.

### Phase 2 — Full Read-Only Registry

Add the remaining 7 read-only tools. Each tool file imports
`_assert_safe_path` from `security.py`, uses `aiosqlite` for index reads,
never contains a `print()` statement.

### Phase 3 — Claude Desktop Integration

```json
{
  "mcpServers": {
    "nexus-audit-v3": {
      "command": "python",
      "args": ["-m", "core.mcp.server"],
      "env": {"NEXUS_LOG_LEVEL": "INFO", "NEXUS_TOOL_TIMEOUT_SECONDS": "180"}
    }
  }
}
```

### Phase 4 — Configuration Tools + Direction Gating

Build the five Group 4 tools with the allowlist and direction
classification from Section 5 from the start — not as a retrofit. Build
`mcp:pending` / `mcp:approve` / `mcp:reject` in the same phase, since the
write tools have no safe default behavior without them.

---

## 11. Testing Specification

### 11.1 Schema Tests (unchanged pattern, extended to Group 4)

```python
def test_finding_hash_rejects_path_traversal():
    with pytest.raises(ValidationError):
        FindingDetailInput(finding_hash="../../.ssh/id_rsa")

def test_scanner_config_rejects_short_reasoning():
    with pytest.raises(ValidationError):
        ScannerConfigInput(scanner_name="bandit", strictness="lenient", reasoning="short")

def test_project_config_rejects_unknown_key():
    with pytest.raises(ValueError, match="not on the allowlist"):
        validate_config_patch({"some_unrecognized_key": True})
```

### 11.2 Direction-Gating Tests (new)

```python
def test_disable_scanner_writes_pending_not_applied():
    result = await disable_scanners(ScannerToggleInput(
        scanner_name="bandit", reasoning="No Python execution paths in this service."
    ))
    assert result["status"] == "pending_approval"
    settings = load_settings(project_id)
    assert settings.scanners["bandit"] is True  # unchanged until approved

def test_enable_scanner_applies_immediately():
    result = await enable_scanners(ScannerToggleInput(
        scanner_name="eslint", reasoning="Adding JS files to this service."
    ))
    assert result["status"] == "success"
    settings = load_settings(project_id)
    assert settings.scanners["eslint"] is True

def test_mcp_approve_applies_pending_change():
    pending_id = await disable_scanners(...)["pending_id"]
    await cli_approve(pending_id)
    settings = load_settings(project_id)
    assert settings.scanners["bandit"] is False
```

### 11.3 STDIO Purity Test (unchanged, still critical)

```python
def test_no_stdout_pollution():
    """Every line on stdout during startup and tool calls is valid JSON-RPC."""
    proc = subprocess.Popen([sys.executable, "-m", "core.mcp.server"], ...)
    # ... send initialize, assert every stdout line parses as JSON-RPC
```

### 11.4 Path Sandbox Tests (unchanged)

```python
def test_sandbox_blocks_ssh_keys():
    with pytest.raises(ValueError, match="outside the sandbox root"):
        _assert_safe_path(str(Path.home() / ".ssh" / "id_rsa"))
```

---

*This document lives on `feature/mcp-server-sqlite-index`, in
`SPCES/MPC/`. It is not merged into `main` and will not be by anyone
other than the project owner, after review.*
