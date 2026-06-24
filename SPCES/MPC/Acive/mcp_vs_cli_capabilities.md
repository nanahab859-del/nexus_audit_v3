# Nexus Audit v3: CLI vs MCP Capabilities Report

This document provides a comprehensive outline of the capabilities available to human users via the Command Line Interface (CLI) versus the autonomous capabilities granted to Claude Desktop via the Model Context Protocol (MCP) server.

## Executive Summary

- **Total CLI Commands (User):** 42
- **Total MCP Tools (Cloud):** 10
- **Overall Capability Coverage:** ~24%

The MCP server is explicitly designed to be a **Read-Heavy Analysis Engine** with limited trigger capabilities. It intentionally strips away administrative, destructive, and configuration commands to ensure AI safety.

---

## Direct Answers to Key Questions

1. **Can the cloud register a project?**
   **No.** The MCP server cannot register a new project. Project registration (`project:register`) requires passing local file paths and validating system access, which is strictly reserved for the human user in the CLI. The cloud can only operate on projects that the user has already registered.

2. **Can it run an audit?**
   **Yes.** The cloud can trigger an audit on any registered project using the `run_project_audit` tool. It can also specify whether to use `--fast` mode. 

3. **Can it do all CLI commands?**
   **No.** The cloud only has access to 10 out of the 42 CLI commands. It lacks access to configuration management (`config:*`), scanner management (`scanner:*`), project deletion (`project:delete`), and manual fix marking (`fix:mark`).

---

## Detailed Comparison Breakdown

### 1. Project Management
| Action | User (CLI) | Cloud (MCP) | Difference / Outreach |
|---|---|---|---|
| List Projects | `project:list` | `list_projects` | Identical capability. |
| Register Project | `project:register` | ❌ **No Access** | Cloud cannot add new paths to the sandbox. |
| Delete Project | `project:delete` / `clear` | ❌ **No Access** | Cloud cannot delete data or drop tables. |
| Set Active Project | `workspace:active` | ❌ **No Access** | Cloud passes the project path/id explicitly per tool call instead of holding session state. |

### 2. Audit Execution & Tracking
| Action | User (CLI) | Cloud (MCP) | Difference / Outreach |
|---|---|---|---|
| Run Audit | `audit:run` | `run_project_audit` | Identical capability. |
| Check Status | `audit:status` | (Built into `run`) | Cloud waits for the job to complete within the `run` tool and returns the status directly. |
| Cancel Audit | `audit:cancel` | ❌ **No Access** | Cloud cannot gracefully abort running jobs. |
| Audit History | `audit:history` | ❌ **No Access** | Cloud only looks at the latest run. |
| Audit Summary | (Viewed in `report`) | `get_latest_audit_summary` | Cloud has a specialized tool to pull JSON counts/scores directly, which is better optimized for LLMs than the CLI text output. |

### 3. Finding Analysis & Fixes
| Action | User (CLI) | Cloud (MCP) | Difference / Outreach |
|---|---|---|---|
| List Findings | `fix:list` | `list_findings` | Cloud has a more rigid paginated tool (max 100). |
| Show Detail | `fix:show` | `get_finding_detail` | Cloud gets the exact JSON tree, but large code structures (>4KB) are safely truncated to prevent context window overflow. |
| View Source Context | (Not natively available) | `get_file_context` | **Cloud Only:** Specialized tool allows the cloud to extract specific vulnerable code snippets for a file. |
| Fix Queue | `fix:queue` | `get_fix_queue` | Identical capability. |
| Mark as Fixed/Note | `fix:mark`, `fix:note` | ❌ **No Access** | Cloud cannot permanently alter the database status of a finding. |

### 4. Advanced Analytics
| Action | User (CLI) | Cloud (MCP) | Difference / Outreach |
|---|---|---|---|
| Diff Runs | `audit:diff` | `diff_runs` | Identical capability. |
| Score Trend | `audit:trend` | `get_trend` | Identical capability. |
| Export SARIF | `audit:export` | ❌ **No Access** | Cloud cannot write export files to the user's disk. |

### 5. Administrative & Configuration (CLI ONLY)
The following categories are **100% restricted** from the Cloud. The user maintains exclusive control over:
- **`config:*`**: The cloud cannot change project settings, quality gates, or retention policies.
- **`scanner:*`**: The cloud cannot install, enable, or disable external security tools (e.g., Bandit, Semgrep).
- **`ai:*`**: The cloud cannot run the internal LLM CLI commands (preventing recursive LLM calls).
- **`report:*`**: The cloud cannot generate physical markdown/PDF reports on disk.
- **`mcp:*`**: The cloud cannot alter its own configuration bridge.

---

## Conclusion & Philosophy

The operational paradigm is defined as **"User Configures, Cloud Analyzes."**

By limiting the Cloud to 24% of the commands, we enforce a strict security boundary. The user is responsible for environment setup, tool installation, project registration, and configuration. Once the guardrails are established, the Cloud acts as a high-speed analytical engine—running the audits, paginating through complex vulnerabilities, and extracting localized code contexts to reason about patches.
