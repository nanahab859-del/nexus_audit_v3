# Nexus Audit MCP Server: Usage & Configuration Guide

**Version:** 2.0 (Updated June 22, 2026 — includes Code Owner expansion tools)  
**Project:** `nexus_audit_v3-mcp-sqlite`  
**Server Name (in Claude Desktop):** `nexus-audit-v3`

---

## 1. Claude Desktop Configuration (Windows → WSL2)

Since Claude Desktop is installed on Windows and Nexus Audit runs inside WSL2 (Ubuntu-22.04), Claude must be configured to launch the MCP server through the WSL bridge.

**Config File Location:**
```
C:\Users\yusup\AppData\Roaming\Claude\claude_desktop_config.json
```
*(Alternatively: Claude Desktop → File → Settings → Developer → Edit Config)*

**Add this entry to your `"mcpServers"` block:**

```json
{
  "mcpServers": {
    "nexus-audit-v3": {
      "command": "wsl.exe",
      "args": [
        "-d",
        "Ubuntu-22.04",
        "-e",
        "bash",
        "-c",
        "source /home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite/.venv/bin/activate && PYTHONPATH=/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite python3 -m core.mcp.server"
      ]
    }
  }
}
```

> **After editing the config you MUST fully quit and reopen Claude Desktop** (not just close the conversation). This kills the old server process and spawns a fresh one with the current code.

---

## 2. Project Addressing

All tools accept a flexible `project_path` argument. You can pass **any** of the following:

| Format | Example |
|---|---|
| Source code path | `/home/yusupha/my_tests/nexus-test-target` |
| Project name | `NexusTestBed` |
| Internal UUID | `530f72b2-0836-4aed-8eee-fc7bd1c10c76` |

The server resolves all three to the internal UUID automatically. **You never need to look up the UUID manually.**

To discover what projects are registered, call `list_projects` first.

---

## 3. Available Tools (15 Total)

The server implements the **Tools** capability only (`resources`, `prompts`, `sampling` are disabled).

### Category: Discovery (no audit required)

| Tool | Description |
|---|---|
| `get_server_info` | Returns server version, MCP spec date, and capability flags. Use this to confirm the server is alive. |
| `list_projects` | Lists all registered projects with their `id`, `name`, and source `path`. Start here before calling any other tool. |

### Category: Audit Execution

| Tool | Input Fields | Notes |
|---|---|---|
| `run_project_audit` | `project_path` (str), `fast_mode` (bool, default `false`) | Triggers a new audit and waits for completion. Returns scores, finding counts, and run ID. |

### Category: Analytics (post-audit — requires at least one completed audit)

| Tool | Key Inputs | Description |
|---|---|---|
| `get_latest_audit_summary` | `project_path` | High-level scores and counts from the most recent run. |
| `list_findings` | `project_path`, `severity`, `category`, `status`, `run_id`, `limit`, `offset` | Paginated finding list. Max 100 per call, default 20. |
| `get_finding_detail` | `finding_hash` | Full context for a single vulnerability by its SHA-256 fingerprint. Large code blocks are safely truncated to 4KB. |
| `get_file_context` | `project_path`, `file_path` | All findings in a specific source file (e.g. `src/auth.py`). Limit default 20, max 50. |
| `get_fix_queue` | `project_path`, `severity_floor`, `limit` | Findings ranked by severity × age × recurrence. `severity_floor` defaults to `HIGH`. |
| `get_trend` | `project_path`, `last_n_runs`, `branch` | Historical score trend. `last_n_runs` default 10, max 50. |
| `diff_runs` | `project_path`, `run_id_a`, `run_id_b` | Structural diff between two audit runs — identifies introduced vs resolved vulnerabilities. |

### Category: Code Owner — Configuration (new in v2)

> All tools in this category write an action record to `~/.nexus_audit/mcp_action_log.txt`. The `reasoning` field is **mandatory** and enforced by the schema (minimum 15 characters). Providing a vague reason (e.g. "reasons") will cause the call to fail with a validation error.

| Tool | Key Inputs | Description |
|---|---|---|
| `enable_scanners` | `project_path`, `scanner_names` (list), `reasoning` | Enables one or more security scanners in the project config. |
| `disable_scanners` | `project_path`, `scanner_names` (list), `reasoning` | Disables one or more scanners. **Requires justification.** |
| `set_scanner_config` | `project_path`, `scanner_name`, `strictness`, `reasoning` | Sets the strictness level for a specific scanner. |
| `set_project_config` | `project_path`, `config_patch` (dict), `reasoning` | Deep-patches any field in the project's `ProjectSettings`. |
| `generate_audit_report` | `project_path`, `output_path` (optional), `format` (`md`\|`json`) | Generates a report file inside the project sandbox. Path traversal is blocked. |

---

## 4. Typical Workflow

### First-time setup
```
1. Call list_projects → confirm your project is visible
2. Call run_project_audit with your project name → wait for completion
3. Call get_latest_audit_summary → review overall health
4. Call get_fix_queue → get prioritized remediation targets
5. Call get_finding_detail with a hash from the fix queue → get full vulnerability context
```

### As Code Owner (configuration workflow)
```
1. Call list_projects → get your project name
2. Call get_latest_audit_summary → assess current state
3. Call enable_scanners or set_scanner_config with a clear reasoning → tune the engine
4. Call run_project_audit again → re-scan with updated config
5. Call generate_audit_report → produce a physical report file
```

---

## 5. Testing the Integration

After restarting Claude Desktop, paste this prompt to run a live end-to-end test:

> "Check your available tools to confirm the `nexus-audit-v3` MCP server is connected. Call `list_projects` to see what projects are registered. Pick `NexusTestBed` (or any listed project) and run a new audit on it. Once the audit completes, fetch the latest summary, then show me the top 3 items from the fix queue."

---

## 6. Logging & Troubleshooting

### MCP Server Logs
All server logs go to `sys.stderr`. Claude Desktop captures stderr automatically.
- View via **Claude Desktop Developer Tools** → MCP tab (if enabled)
- Or check the Windows Claude Desktop log files

### Audit Engine Logs
Detailed scanner execution logs are inside WSL:
```
~/.nexus_audit/projects/<project_uuid>/jobs/<job_id>/audit.log
```

### Code Owner Action Audit Trail
Every scanner or config change made via the Code Owner tools is logged here:
```
~/.nexus_audit/mcp_action_log.txt
```
Each line records: `[ACTION] Target: <name> | Reason: <reasoning text>`

### Stale Server (Most Common Issue)
If tools fail or `list_projects` is missing, **quit and fully reopen Claude Desktop**. The server process runs from when Claude Desktop launches — code changes on disk are not picked up until the process is restarted.
