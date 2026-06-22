# Nexus Audit V3 — MCP Server Technical Specification

**Document type:** Technical Specification  
**Protocol revision pinned to:** `2025-06-18` (MCP specification, latest stable)  
**Status:** Ready for Implementation  
**Version:** 1.0.0  
**Date:** June 2026  

---

## Table of Contents

1. [Research Validation](#1-research-validation)
2. [Paradigm: MRI and Surgeon](#2-paradigm-mri-and-surgeon)
3. [Architecture Overview](#3-architecture-overview)
4. [Communication Protocol](#4-communication-protocol)
5. [Tool Registry — Full Specification](#5-tool-registry--full-specification)
6. [Data Contracts — Surgical JSON Payloads](#6-data-contracts--surgical-json-payloads)
7. [Security Model and Threat Mitigation](#7-security-model-and-threat-mitigation)
8. [Failure Mode Catalogue](#8-failure-mode-catalogue)
9. [Implementation Guide](#9-implementation-guide)
10. [Configuration Reference](#10-configuration-reference)
11. [Testing Specification](#11-testing-specification)

---

## 1. Research Validation

The research brief provided is substantially correct. The following table records what has been confirmed by independent source checking, what requires an update, and what was missing from the brief entirely. The specification downstream of this section incorporates all corrections.

### 1.1 Confirmed Accurate

| Claim in Brief | Status | Evidence |
|---|---|---|
| FastMCP uses decorator syntax (`@mcp.tool()`) | ✅ Confirmed | Official SDK examples; `from mcp.server.fastmcp import FastMCP` is the correct import path |
| STDIO is the correct transport for local integrations | ✅ Confirmed | MCP spec 2025-06-18 designates stdio as standard for local tooling |
| JSON-RPC 2.0 is the message format | ✅ Confirmed | MCP specification, all versions |
| STDIO stdout corruption trap is real | ✅ Confirmed | Multiple production incident reports; any `print()` to stdout corrupts the JSON-RPC stream |
| Stateful connection instability under concurrent asyncio tasks | ✅ Confirmed | GitHub issue #1221 (strands-agents), #671 (python-sdk): tool execution hangs indefinitely when asyncio subprocesses overlap with the stdio handler |
| Read-only server design prevents the Confused Deputy attack | ✅ Confirmed | Accepted MCP security pattern |
| Pydantic input validation is the correct mitigation for command injection | ✅ Confirmed | Standard practice; FastMCP performs automatic schema inference from Pydantic models |

### 1.2 Corrections Required

| Claim in Brief | Issue | Correction Applied |
|---|---|---|
| "FastMCP is part of the official `modelcontextprotocol/python-sdk`" | Partially misleading. FastMCP 3.x is maintained by **Prefect**, not Anthropic. The import path `from mcp.server.fastmcp import FastMCP` still works via the Anthropic SDK, but the high-level FastMCP framework is a separate package (`pip install fastmcp`). The two are compatible but distinct. | Specification uses `fastmcp>=3.0` as a direct dependency. The Anthropic low-level SDK is a transitive dependency. |
| No MCP spec version pinned | The brief references MCP behaviour without pinning a spec version, which leads to ambiguous behaviour under SDK upgrades. | All tool schemas and transport behaviour in this spec are pinned to **protocol revision 2025-06-18**. |

### 1.3 Failure Modes Not in the Brief (Discovered by Research)

These must be mitigated in the implementation. Sections 8.4 through 8.6 cover the fixes.

| Issue | Source |
|---|---|
| **Undetected server termination**: when the server process crashes, the STDIO client does not raise a transport error. It hangs indefinitely. | GitHub issue #396 (python-sdk) |
| **Windows asyncio + STDIO bug**: Python's `_overlapped` module fails to initialise STDIO pipes on Windows, causing silent hangs or `ClosedResourceError`. | Windows fix guide; GitHub issue #671 |
| **macOS Python 3.12 KqueueSelector hang**: the server hangs immediately after startup on macOS with Python 3.12 when using the low-level SDK. FastMCP 3.x mitigates this. | GitHub issue #547 |
| **Default request timeout (-32001 errors)**: MCP clients default to a 60-second tool timeout. Long-running `run_project_audit` calls will be killed mid-execution without a timeout override. | MCP troubleshooting guide, 2025 |

---

## 2. Paradigm: MRI and Surgeon

Nexus Audit V3 acts as the **MRI** — a diagnostic instrument that produces high-fidelity, stateful context about a codebase. The external AI agent acts as the **Surgeon** — the entity that reads the diagnostic and performs code mutations.

The boundary between the two is absolute:

```
┌────────────────────────────────────────────────────────────────┐
│                     NEXUS MCP SERVER                           │
│              (Diagnostic only — never writes code)             │
│                                                                │
│  ● Runs audit analysis                                         │
│  ● Reads from ~/.nexus_audit/ (sandboxed)                      │
│  ● Returns structured JSON findings                            │
│  ● Tracks state: scores, history, fix queue                    │
│                                                                │
│  ✗ Cannot write files                                          │
│  ✗ Cannot execute shell commands                               │
│  ✗ Cannot read outside ~/.nexus_audit/                         │
└────────────────────────────────────────────────────────────────┘
                          │  JSON-RPC 2.0
                          │  over STDIO
                          ▼
┌────────────────────────────────────────────────────────────────┐
│                   EXTERNAL AI AGENT                            │
│                (Code mutation — never reads DB)                │
│                                                                │
│  ● Calls Nexus tools to get context                            │
│  ● Uses its OWN filesystem tools to edit code                  │
│  ● Calls run_project_audit to verify each fix                  │
│  ● Iterates until findings are resolved                        │
└────────────────────────────────────────────────────────────────┘
```

### 2.1 The Autonomous Verification Loop

```
1. DISCOVERY     Agent calls list_tools → receives all 9 Nexus tool schemas

2. BASELINE      Agent calls run_project_audit → receives run_id
                 Agent calls get_latest_audit_summary → receives scores + counts

3. PRIORITISE    Agent calls get_fix_queue(severity_floor="CRITICAL", limit=5)
                 Agent calls get_finding_detail(finding_hash) for each item

4. FIX           Agent uses its OWN file-edit tools to modify source code
                 (Nexus does not participate in this step)

5. VERIFY        Agent calls run_project_audit again → receives new run_id
                 Agent calls diff_runs(run_id_old, run_id_new)

6. ITERATE       If new CRITICAL findings = 0 and score_delta > 0 → DONE
                 Otherwise → return to step 3 with updated context
```

---

## 3. Architecture Overview

### 3.1 Process Topology

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
│   ├── Tool handlers (9 read-only tools)
│   ├── Nexus DB client (reads nexus_state.db)
│   └── Audit engine (runs scans on demand)
│
└── ~/.nexus_audit/
    └── projects/<project_id>/
        ├── nexus_state.db       ← SQLite index (read + trigger)
        └── jobs/<job_id>/
            ├── audit_data_complete.json
            └── audit_summary.json
```

### 3.2 Package Dependencies

```toml
# pyproject.toml

[project]
name = "nexus-audit-mcp"
requires-python = ">=3.11"

dependencies = [
    "fastmcp>=3.0,<4",         # FastMCP 3.x (maintained by Prefect)
    "mcp>=1.25,<2",            # Official Anthropic MCP SDK (transitive)
    "pydantic>=2.5",           # Input validation + schema generation
    "anyio>=4.0",              # Async I/O (required by MCP SDK)
    "aiosqlite>=0.20",         # Async SQLite reads
]
```

> **Note on FastMCP vs. low-level SDK:** FastMCP 3.x wraps the official `mcp` SDK. It handles schema generation from Python type annotations, input validation, and transport negotiation automatically. Using FastMCP directly reduces boilerplate by approximately 80% compared to the low-level `mcp.server.lowlevel` API. The low-level API is not recommended for this project.

---

## 4. Communication Protocol

### 4.1 Transport: STDIO

The server runs as a subprocess spawned by the MCP host. There are no network ports. The process is invisible to the external internet.

```
stdin  → JSON-RPC 2.0 requests from the agent host
stdout → JSON-RPC 2.0 responses to the agent host
stderr → ALL server logging (never stdout — see Section 8.1)
```

### 4.2 JSON-RPC 2.0 Message Format

**Request (agent → server):**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "get_finding_detail",
    "arguments": {
      "finding_hash": "a8f9c2b4..."
    }
  }
}
```

**Response (server → agent):**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"finding_hash\": \"a8f9c2b4...\", ...}"
      }
    ],
    "isError": false
  }
}
```

**Error response:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32602,
    "message": "Invalid params: finding_hash must be a 64-character hex string"
  }
}
```

### 4.3 Session Lifecycle

```
Agent host spawns process → MCP initialize handshake → tools/list
                                                              ↓
                                              tools/call (repeated)
                                                              ↓
Agent host kills process → SIGTERM → server cleanup → process exit
```

The server must handle `SIGTERM` gracefully by flushing any in-progress SQLite write and exiting cleanly. Abrupt process death without SIGTERM handling is the primary cause of the client-side hang described in Section 8.4.

---

## 5. Tool Registry — Full Specification

Nine tools are exposed. All are **read-only**. No tool may write files, execute arbitrary shell commands, or read paths outside the sandboxed directory.

---

### Tool 1: `get_server_info`

**Purpose:** Returns server version, MCP spec version, and supported capabilities. The agent should call this first to verify compatibility.

```python
@mcp.tool()
def get_server_info() -> dict:
    """Return Nexus MCP server version and supported capabilities."""
    return {
        "server": "nexus-audit-v3-mcp",
        "version": "1.0.0",
        "mcp_spec": "2025-06-18",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
            "sampling": False
        },
        "read_only": True,
        "sandbox_root": str(Path.home() / ".nexus_audit")
    }
```

**Input schema:** None  
**Output:** JSON object  
**Max response size:** < 1 KB  

---

### Tool 2: `run_project_audit`

**Purpose:** Trigger a new audit scan of the specified project. Returns a `run_id` the agent uses for all subsequent queries. This is the only tool that has a side effect — it creates JSON and SQLite records — but it does not modify source code.

```python
class RunAuditInput(BaseModel):
    project_path: str = Field(
        description="Absolute path to the project root to audit",
        min_length=1,
        max_length=4096
    )
    fast_mode: bool = Field(
        default=False,
        description="If true, runs summary scan only (no coupling matrix). Faster."
    )

@mcp.tool()
async def run_project_audit(input: RunAuditInput) -> dict:
    """Run a full Nexus audit on the specified project. Returns run_id."""
    ...
```

**Input schema:**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `project_path` | `string` | Yes | Must exist on disk; must not contain `..`; validated by `_assert_safe_path()` |
| `fast_mode` | `boolean` | No | Default: `false` |

**Output:**
```json
{
  "run_id": "2026-06-15T14-32-01Z_a3f9c2b",
  "status": "complete",
  "duration_ms": 4820,
  "scores": {
    "overall": 82.4,
    "security": 78.1,
    "quality": 88.0
  },
  "counts": {
    "total": 47,
    "critical": 1,
    "high": 5
  }
}
```

**Timeout:** Tool execution may take up to 120 seconds for large projects. The MCP client timeout must be raised accordingly (see Section 10.2).  
**Error codes:** `INVALID_PATH` · `PATH_OUTSIDE_SANDBOX` · `AUDIT_FAILED`

---

### Tool 3: `get_latest_audit_summary`

**Purpose:** Return the summary of the most recent audit run for a project. Used to establish baseline context without transmitting a large payload.

```python
class ProjectInput(BaseModel):
    project_path: str = Field(description="Absolute path to the project root")

@mcp.tool()
async def get_latest_audit_summary(input: ProjectInput) -> dict:
    """Return the summary of the most recent audit for this project."""
    ...
```

**Output:** Same schema as `run_project_audit` output, plus `run_id` and `git` context. Payload stays under 10 KB.

---

### Tool 4: `get_finding_detail` ⭐ Core Surgical Tool

**Purpose:** Return the full structural detail of a single finding by its hash. This is the primary mechanism for giving the agent actionable, non-hallucination-inducing context about a specific vulnerability. Returns only what is needed to fix one finding.

```python
class FindingDetailInput(BaseModel):
    finding_hash: str = Field(
        description="SHA-256 fingerprint of the finding",
        pattern=r"^[a-f0-9]{8,64}$"
    )

@mcp.tool()
async def get_finding_detail(input: FindingDetailInput) -> dict:
    """Return full structural detail for a single finding by its hash."""
    ...
```

**Output — the surgical JSON payload:**
```json
{
  "finding_hash": "a8f9c2b4d6e1f3...",
  "rule_id": "PREVENT_SQL_INJECTION",
  "severity": "CRITICAL",
  "category": "security",
  "status": "open",
  "file_path": "src/auth/login.py",
  "git_pointer": {
    "commit": "a3f9c2b",
    "lines": [87, 92]
  },
  "structural_context": {
    "ast_node_type": "CallExpression",
    "vulnerable_sink": "cursor.execute(query)",
    "data_flow_source": {
      "variable_name": "user_input",
      "line": 42
    }
  },
  "message": "String interpolation into cursor.execute() allows SQL injection. Use parameterised queries.",
  "first_seen_run": "2026-06-08T10-12-00Z_abc1234",
  "age_days": 7
}
```

**Max response size:** < 5 KB per finding. If `structural_context` exceeds 4 KB, it is truncated and a `context_truncated: true` flag is added.

---

### Tool 5: `list_findings`

**Purpose:** Return a paginated list of findings for a project. Agents use this to survey the fix landscape before diving into individual `get_finding_detail` calls.

```python
class ListFindingsInput(BaseModel):
    project_path: str
    run_id: str | None = Field(default=None, description="Specific run; defaults to latest")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] | None = None
    category: Literal["security", "quality", "complexity", "dependencies"] | None = None
    status: Literal["open", "suppressed", "resolved"] = "open"
    limit: int = Field(default=20, ge=1, le=100)  # Hard cap: never more than 100
    offset: int = Field(default=0, ge=0)

@mcp.tool()
async def list_findings(input: ListFindingsInput) -> dict:
    """Return a paginated list of findings. Hard limit: 100 per call."""
    ...
```

**Output:**
```json
{
  "total": 47,
  "returned": 20,
  "offset": 0,
  "findings": [
    {
      "finding_hash": "a8f9c2b4...",
      "rule_id": "PREVENT_SQL_INJECTION",
      "severity": "CRITICAL",
      "file_path": "src/auth/login.py",
      "line_start": 87,
      "status": "open"
    }
  ]
}
```

> **Context window protection:** The hard `limit=100` cap is enforced server-side regardless of what the agent requests. Returning 10,000 findings to an LLM causes context window exhaustion, hallucinations, and crashed requests. The agent must paginate using `offset`.

---

### Tool 6: `get_fix_queue`

**Purpose:** Return a ranked fix queue — findings ordered by `severity × age × recurrence_count`. This gives the agent a prioritised work order, not just a flat list.

```python
class FixQueueInput(BaseModel):
    project_path: str
    severity_floor: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "HIGH"
    limit: int = Field(default=10, ge=1, le=50)

@mcp.tool()
async def get_fix_queue(input: FixQueueInput) -> dict:
    """Return the ranked fix queue for this project."""
    ...
```

**Output:**
```json
{
  "queue": [
    {
      "rank": 1,
      "finding_hash": "a8f9c2b4...",
      "rule_id": "PREVENT_SQL_INJECTION",
      "severity": "CRITICAL",
      "file_path": "src/auth/login.py",
      "age_days": 7,
      "score_impact": 14.1,
      "recurrence_count": 3
    }
  ]
}
```

---

### Tool 7: `get_trend`

**Purpose:** Return the score trend for the last N runs. Used by the agent to determine whether it is making overall progress across an iterative fix session.

```python
class TrendInput(BaseModel):
    project_path: str
    last_n_runs: int = Field(default=10, ge=2, le=50)
    branch: str | None = Field(default=None, description="Filter to a specific git branch")

@mcp.tool()
async def get_trend(input: TrendInput) -> dict:
    """Return score trend across the last N audit runs."""
    ...
```

**Output:** Reads from SQLite in O(log N). Response is always under 20 KB regardless of `last_n_runs`.

```json
{
  "project_path": "/home/user/myapp",
  "branch_filter": "main",
  "runs": [
    {
      "run_id": "2026-06-08T10-12-00Z_abc1234",
      "timestamp": "2026-06-08T10:12:00Z",
      "git_commit": "abc1234",
      "scores": { "overall": 91.2, "security": 88.0 },
      "counts": { "critical": 0, "high": 2 }
    }
  ]
}
```

---

### Tool 8: `diff_runs`

**Purpose:** Return a structural diff between two audit runs. This is the primary tool for the agent to verify whether its code edits produced the expected improvement.

```python
class DiffInput(BaseModel):
    project_path: str
    run_id_a: str = Field(description="The older run (baseline)")
    run_id_b: str = Field(description="The newer run (after fix)")

@mcp.tool()
async def diff_runs(input: DiffInput) -> dict:
    """Return structural diff between two audit runs."""
    ...
```

**Output:**
```json
{
  "run_id_a": "2026-06-08T10-12-00Z_abc1234",
  "run_id_b": "2026-06-15T14-32-01Z_a3f9c2b",
  "score_delta": {
    "overall": -9.2,
    "security": -14.1,
    "quality": 4.9
  },
  "new_findings": {
    "count": 8,
    "by_severity": { "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 2 },
    "hashes": ["a8f9c2b4...", "d6e1f3a2..."]
  },
  "resolved_findings": {
    "count": 3,
    "hashes": ["b3c9d1e5...", "f4a2b8c6...", "e7d3f1a9..."]
  },
  "coupling_changes": {
    "added_edges": [["auth", "payments"]],
    "removed_edges": [["utils", "database"]]
  },
  "probable_commit": "a3f9c2b"
}
```

---

### Tool 9: `get_file_context`

**Purpose:** Return all open findings for a specific file. Used when the agent is about to edit a file and wants to understand the full picture of issues in that file before touching it.

```python
class FileContextInput(BaseModel):
    project_path: str
    file_path: str = Field(description="Path relative to project root, e.g. src/auth/login.py")
    limit: int = Field(default=20, ge=1, le=50)

@mcp.tool()
async def get_file_context(input: FileContextInput) -> dict:
    """Return all open findings for a specific file."""
    ...
```

**Path safety:** `file_path` is joined to `project_path` using `Path.resolve()`. If the resolved path does not start with `project_path`, the call is rejected with `PATH_OUTSIDE_PROJECT`.

---

## 6. Data Contracts — Surgical JSON Payloads

The guiding constraint is: **never send more tokens to the agent than are needed for the next single action.**

| Tool | Typical Payload | Max Payload | Context Window Impact |
|---|---|---|---|
| `get_server_info` | < 0.5 KB | 1 KB | Negligible |
| `run_project_audit` | 1–3 KB | 5 KB | Negligible |
| `get_latest_audit_summary` | 3–8 KB | 10 KB | Negligible |
| `get_finding_detail` | 1–4 KB | 5 KB | Negligible |
| `list_findings` (limit=20) | 4–8 KB | 12 KB | Negligible |
| `get_fix_queue` (limit=10) | 2–5 KB | 8 KB | Negligible |
| `get_trend` (last=10) | 3–8 KB | 20 KB | Negligible |
| `diff_runs` | 3–10 KB | 15 KB | Negligible |
| `get_file_context` | 2–6 KB | 8 KB | Negligible |

**The full audit payload (`audit_data_complete.json`) is never transmitted to the agent.** It may be 5–50 MB. Sending it would exhaust the context window, cause hallucinations, and generate extremely high API costs. All agent access to audit data is mediated through the above tools, which read only the required subset from SQLite.

---

## 7. Security Model and Threat Mitigation

### 7.1 Threat Model

The server runs locally and communicates with an external LLM. Three attack surfaces exist:

1. **The LLM itself** — can hallucinate dangerous tool calls or be manipulated by prompt injection in code comments it read.
2. **The agent host** — can be compromised or misconfigured.
3. **The local filesystem** — the server has read access and must not be used as a pivot to exfiltrate sensitive files.

### 7.2 The Confused Deputy — Mitigation

The Confused Deputy attack occurs when the server, holding elevated permissions, is tricked by the agent into performing actions on its behalf that the agent could not perform directly.

**Mitigation: 100% read-only server.**

No tool writes files, executes shell commands, or modifies any system state except creating audit archives (which the agent cannot access directly). The server has no delete capability.

```python
# THIS IS THE COMPLETE PROHIBITED OPERATIONS LIST
# No tool may contain any of the following:

import subprocess; subprocess.run(...)        # PROHIBITED — no shell execution
import os; os.unlink(...)                     # PROHIBITED — no file deletion
open(path, "w")                              # PROHIBITED — no file writes
shutil.rmtree(...)                           # PROHIBITED — no directory removal
eval(...)                                    # PROHIBITED — no code execution
exec(...)                                    # PROHIBITED — no code execution
```

### 7.3 Command Injection — Mitigation

**Never pass agent-supplied strings to shell execution.** This is enforced at two levels:

**Level 1 — Pydantic validation on every tool input:**
```python
class FindingDetailInput(BaseModel):
    finding_hash: str = Field(
        pattern=r"^[a-f0-9]{8,64}$"  # Only hex chars. SQL injection impossible.
    )
```

**Level 2 — Parameterised SQLite queries only:**
```python
# CORRECT — parameterised query
cursor.execute(
    "SELECT * FROM findings WHERE fingerprint = ?",
    (input.finding_hash,)
)

# WRONG — never do this
cursor.execute(f"SELECT * FROM findings WHERE fingerprint = '{input.finding_hash}'")
```

### 7.4 Data Exfiltration / Scope Creep — Mitigation

The server must only be able to read from `~/.nexus_audit/`. It must not be able to read `~/.ssh/id_rsa`, environment variables, or any other sensitive file even if the agent requests it.

```python
SANDBOX_ROOT = Path.home() / ".nexus_audit"

def _assert_safe_path(raw_path: str) -> Path:
    """Resolve and validate that a path is within the sandbox root.
    
    Raises ValueError if the resolved path escapes the sandbox.
    This blocks path traversal attacks like '../../.ssh/id_rsa'.
    """
    try:
        resolved = Path(raw_path).resolve()
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path: {e}") from e

    if not str(resolved).startswith(str(SANDBOX_ROOT)):
        raise ValueError(
            f"Path '{resolved}' is outside the sandbox root '{SANDBOX_ROOT}'. "
            "The Nexus MCP server can only read from ~/.nexus_audit/."
        )
    return resolved
```

`_assert_safe_path()` must be called at the start of every tool handler that accepts a path argument.

### 7.5 Security Invariants (Non-Negotiable)

These invariants must pass in the test suite before any version is released:

- [ ] No tool handler calls `subprocess.run()`, `os.system()`, `exec()`, or `eval()`
- [ ] No tool handler opens a file for writing (`open(..., "w")`)
- [ ] Every `project_path` input is validated by `_assert_safe_path()` before use
- [ ] Every `finding_hash` input matches `/^[a-f0-9]{8,64}$/` before database query
- [ ] Every SQLite query uses `?` parameter substitution — zero string formatting
- [ ] `limit` values are capped server-side regardless of agent request (100 max)
- [ ] All logging goes to `stderr` only — zero `print()` calls

---

## 8. Failure Mode Catalogue

### 8.1 STDIO Stdout Corruption (Critical — Confirmed)

**What happens:** Any output to stdout that is not a valid JSON-RPC message corrupts the MCP stream. The agent host throws a protocol error and the connection dies. A single `print("debugging")` statement anywhere in the server codebase — including in transitive dependencies — causes this.

**Mitigation — mandatory logging configuration (must be first thing in `server.py`):**

```python
import logging
import sys

# CRITICAL: ALL logging must go to stderr.
# Never use print(). Never allow any output to stdout except JSON-RPC.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)

logger = logging.getLogger("nexus.mcp")

# Silence any third-party library that might print to stdout
for noisy_lib in ["httpx", "httpcore", "urllib3", "anyio"]:
    logging.getLogger(noisy_lib).setLevel(logging.WARNING)
```

**Detecting violations:** Run the test in Section 11.3.

---

### 8.2 Concurrent asyncio Deadlock (Confirmed)

**What happens:** If the agent host calls two tools simultaneously, or if a background audit task overlaps with a tool handler, the asyncio event loop can deadlock. The tool call hangs indefinitely.

**Mitigation — per-project asyncio lock:**

```python
from asyncio import Lock
from collections import defaultdict

_project_locks: dict[str, Lock] = defaultdict(Lock)

async def _with_project_lock(project_path: str, coro):
    """Ensure only one audit runs at a time per project."""
    async with _project_locks[project_path]:
        return await coro
```

Wrap `run_project_audit` and `diff_runs` (the two stateful tools) with this lock. Read-only tools (`get_finding_detail`, `list_findings`, etc.) do not need the lock.

---

### 8.3 Data Pagination — Context Window Exhaustion (Design Requirement)

**What happens:** An agent (via hallucination or direct request) calls `list_findings(limit=10000)`. The server returns 50 MB of JSON. The LLM's context window is exhausted, the request crashes, and API costs spike.

**Mitigation — server-side hard caps enforced by Pydantic before hitting the database:**

| Tool | Hard Cap |
|---|---|
| `list_findings` | 100 findings per call |
| `get_fix_queue` | 50 items per call |
| `get_trend` | 50 runs per call |
| `get_file_context` | 50 findings per call |
| `get_finding_detail` | structural_context truncated at 4 KB |

The agent must paginate using `offset`. The response always includes `total` so the agent knows how many pages remain.

---

### 8.4 Undetected Server Termination — Client Hang (Discovered)

**What happens:** If the server crashes (unhandled exception, SIGKILL, out of memory), the MCP client does not receive a transport error. It waits indefinitely for a response that will never come, blocking all subsequent agent actions.

**Mitigation — application-level timeout + graceful SIGTERM handling:**

```python
import signal
import asyncio

async def _handle_sigterm():
    """Flush in-progress work and exit cleanly on SIGTERM."""
    logger.info("SIGTERM received — flushing and exiting", file=sys.stderr)
    # Allow in-flight async tasks to complete (max 5s)
    await asyncio.sleep(0)
    raise SystemExit(0)

# In server entrypoint:
loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(_handle_sigterm()))
```

The agent host must also set `TOOL_CALL_TIMEOUT = 180` seconds (three minutes) in its MCP configuration. After that, it should treat a non-response as a server crash and restart the process.

---

### 8.5 Windows asyncio + STDIO Incompatibility (Discovered)

**What happens:** On Windows, Python's asyncio uses `ProactorEventLoop` which has known issues initialising STDIO pipes for subprocess-spawned MCP servers. Symptoms: silent hang on startup, or `ClosedResourceError` during the first tool call.

**Mitigation:**

```python
# In server.py, before any asyncio imports:
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

Add a note to the README: "Windows requires Python ≥ 3.12.4 and the above event loop policy override."

---

### 8.6 Long-Running Audit Timeouts — Error -32001 (Discovered)

**What happens:** MCP clients default to a 60-second timeout on tool calls. `run_project_audit` on a large project may take 120+ seconds. The client kills the call with error `-32001` before the audit completes.

**Mitigation:** Document this in the agent host configuration (Section 10.2). The server-side `run_project_audit` tool should also stream progress notifications if the MCP host supports it:

```python
@mcp.tool()
async def run_project_audit(input: RunAuditInput, ctx: Context) -> dict:
    """Trigger a Nexus audit. May take up to 120 seconds for large projects."""
    await ctx.report_progress(0, 100, "Starting scan...")
    # ... run scan in phases ...
    await ctx.report_progress(50, 100, "Security analysis complete...")
    await ctx.report_progress(100, 100, "Audit complete")
    return result
```

---

## 9. Implementation Guide

### 9.1 Phase 1 — Minimal Working Server (Ship First)

Stand up a server with three tools: `get_server_info`, `run_project_audit`, `get_latest_audit_summary`. Confirm the STDIO transport works with a real agent host before building the remaining six tools.

**server.py — entrypoint:**

```python
import sys
import logging
import signal
import asyncio
from pathlib import Path

# STEP 1: Configure logging — MUST be before any other imports that might log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("nexus.mcp.server")

# STEP 2: Windows event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# STEP 3: FastMCP server instance
from fastmcp import FastMCP

mcp = FastMCP(
    name="nexus-audit-v3",
    version="1.0.0",
    instructions=(
        "You are connected to Nexus Audit V3, a local code analysis platform. "
        "Use run_project_audit to trigger scans, then get_finding_detail for "
        "individual findings. All data stays on the developer's machine. "
        "This server is read-only — you must use your own file tools to edit code."
    )
)

# STEP 4: Import tool modules (each in its own file)
from .tools.audit import run_project_audit, get_latest_audit_summary
from .tools.findings import get_finding_detail, list_findings, get_file_context
from .tools.queue import get_fix_queue
from .tools.history import get_trend, diff_runs
from .tools.info import get_server_info

# STEP 5: Register tools
for tool_fn in [
    get_server_info, run_project_audit, get_latest_audit_summary,
    get_finding_detail, list_findings, get_file_context,
    get_fix_queue, get_trend, diff_runs
]:
    mcp.tool()(tool_fn)

# STEP 6: SIGTERM handler
def _handle_sigterm(signum, frame):
    logger.info("SIGTERM received — shutting down cleanly")
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)

# STEP 7: Run
if __name__ == "__main__":
    logger.info("Nexus MCP Server starting (transport=stdio)")
    mcp.run(transport="stdio")
```

**Checkpoint:** After wiring `get_server_info` only, test with the MCP inspector:
```bash
npx @modelcontextprotocol/inspector python -m nexus.mcp.server
```
The inspector should list one tool. No errors in stderr.

### 9.2 Phase 2 — Full Tool Registry

Add the remaining eight tools. Each tool file should:
- Import `_assert_safe_path` from a shared `security.py` module
- Use `aiosqlite` for all database reads
- Have its own `logger = logging.getLogger("nexus.mcp.tools.<name>")`
- Never contain a `print()` statement

### 9.3 Phase 3 — Claude Desktop Integration

**`claude_desktop_config.json` entry:**

```json
{
  "mcpServers": {
    "nexus-audit-v3": {
      "command": "python",
      "args": ["-m", "nexus.mcp.server"],
      "env": {
        "NEXUS_LOG_LEVEL": "INFO",
        "NEXUS_TOOL_TIMEOUT_SECONDS": "180"
      }
    }
  }
}
```

Restart Claude Desktop after editing this file. The Nexus tools will appear in the tools panel.

---

## 10. Configuration Reference

### 10.1 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXUS_LOG_LEVEL` | `INFO` | Logging level. `DEBUG` for development. All output goes to stderr. |
| `NEXUS_TOOL_TIMEOUT_SECONDS` | `180` | Maximum seconds for `run_project_audit` before raising a timeout error. |
| `NEXUS_MAX_FINDINGS_PER_CALL` | `100` | Hard server-side cap on `list_findings` limit. Cannot be exceeded by agent. |
| `NEXUS_SANDBOX_ROOT` | `~/.nexus_audit` | Root of the sandboxed read zone. Paths outside this are rejected. |
| `NEXUS_AUDIT_FAST_MODE` | `false` | If `true`, coupling matrix analysis is skipped for speed. |

### 10.2 Agent Host Timeout Configuration

The default MCP tool call timeout (60 seconds) is too short for `run_project_audit`. Override it in each agent host:

| Host | Override Method |
|---|---|
| Claude Desktop | Set `NEXUS_TOOL_TIMEOUT_SECONDS=180` in `env` block |
| Cursor | MCP server settings → `toolTimeout: 180000` (milliseconds) |
| Custom agent | Pass `timeout=180` to the MCP client session constructor |

---

## 11. Testing Specification

### 11.1 Unit Tests — Tool Schemas

Every tool must have a test that constructs its input model with valid and invalid data:

```python
import pytest
from pydantic import ValidationError
from nexus.mcp.tools.findings import FindingDetailInput

def test_finding_hash_valid():
    m = FindingDetailInput(finding_hash="a8f9c2b4d6e1f3a9")
    assert m.finding_hash == "a8f9c2b4d6e1f3a9"

def test_finding_hash_rejects_sql_injection():
    with pytest.raises(ValidationError):
        FindingDetailInput(finding_hash="' OR 1=1; --")

def test_finding_hash_rejects_path_traversal():
    with pytest.raises(ValidationError):
        FindingDetailInput(finding_hash="../../.ssh/id_rsa")
```

### 11.2 Security Tests — Path Sandbox

```python
from nexus.mcp.security import _assert_safe_path
import pytest

def test_sandbox_allows_nexus_root(tmp_path):
    # Patching SANDBOX_ROOT to tmp_path for the test
    path = _assert_safe_path(str(tmp_path / "projects" / "abc123"))
    assert str(path).startswith(str(tmp_path))

def test_sandbox_blocks_ssh_keys():
    with pytest.raises(ValueError, match="outside the sandbox root"):
        _assert_safe_path(str(Path.home() / ".ssh" / "id_rsa"))

def test_sandbox_blocks_traversal():
    with pytest.raises(ValueError, match="outside the sandbox root"):
        _assert_safe_path("/tmp/../../../etc/passwd")
```

### 11.3 STDIO Purity Test (Critical)

This test verifies that the server emits zero bytes to stdout during startup and tool execution, except for valid JSON-RPC messages:

```python
import subprocess, json, sys

def test_no_stdout_pollution():
    """Starts the MCP server, sends an initialize request, and checks
    that every line on stdout is valid JSON-RPC 2.0."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "nexus.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    init_request = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18",
                   "clientInfo": {"name": "test", "version": "0.0.1"},
                   "capabilities": {}}
    }) + "\n"

    stdout, stderr = proc.communicate(input=init_request.encode(), timeout=10)

    for line in stdout.decode().strip().split("\n"):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            assert "jsonrpc" in parsed, f"Non-JSON-RPC line on stdout: {line!r}"
        except json.JSONDecodeError:
            raise AssertionError(f"Non-JSON line on stdout: {line!r}")
```

### 11.4 Integration Test — Autonomous Loop

```python
async def test_autonomous_fix_loop():
    """Simulates one complete agent iteration: audit → list → detail → diff."""
    async with mcp_test_client() as client:
        # Step 1: Run baseline audit
        result = await client.call_tool("run_project_audit",
                                        {"project_path": TEST_PROJECT})
        run_id_a = result["run_id"]
        assert result["status"] == "complete"

        # Step 2: Get fix queue
        queue = await client.call_tool("get_fix_queue",
                                       {"project_path": TEST_PROJECT,
                                        "severity_floor": "HIGH", "limit": 3})
        assert len(queue["queue"]) >= 1

        # Step 3: Get detail for top item
        detail = await client.call_tool("get_finding_detail",
                                        {"finding_hash": queue["queue"][0]["finding_hash"]})
        assert "structural_context" in detail

        # Step 4: (Agent would fix code here — skipped in unit test)

        # Step 5: Run verification audit
        result2 = await client.call_tool("run_project_audit",
                                         {"project_path": TEST_PROJECT})
        run_id_b = result2["run_id"]

        # Step 6: Diff
        diff = await client.call_tool("diff_runs",
                                      {"project_path": TEST_PROJECT,
                                       "run_id_a": run_id_a,
                                       "run_id_b": run_id_b})
        assert "score_delta" in diff
        assert "new_findings" in diff
        assert "resolved_findings" in diff
```

---

*Nexus Audit V3 MCP Server Specification v1.0.0 — June 2026*  
*Pinned to MCP protocol revision: 2025-06-18*  
*Commit this document alongside the server source code. When the tool list changes, update this document in the same pull request.*
