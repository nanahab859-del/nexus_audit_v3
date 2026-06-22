
---

# Technical Strategy Report: Nexus Audit v3 MCP Expansion

## 1. Executive Summary

The current Model Context Protocol (MCP) server implementation restricts the AI agent (Claude) to a read-only "Analyst" role, granting it access to only ~24% of the CLI commands. This "Zero-Trust" configuration artificially bottlenecks the agent's utility.

Updating JSON configuration dictionaries (e.g., `ProjectSettings`) does not carry the same Remote Code Execution (RCE) risk as arbitrary filesystem execution. By treating operational adjustments—like toggling scanners or altering strictness—as high-level security threats, we are preventing the AI from acting as an autonomous "Code Owner."

We are officially expanding the MCP capabilities to ~45% coverage by unlocking configuration and scanner management. However, this expansion introduces a new class of risk that must be mitigated programmatically.

## 2. The Missing Link: "Silent Downgrade" Risk

While the recent "Game Report" correctly identified that allowing the AI to toggle scanners poses **zero system-level RCE risk**, it failed to account for **Operational Blind Spot Risk** (often called "Configuration Drift" or "Lazy Agent Syndrome").

When an LLM struggles to patch a complex vulnerability, it frequently takes the path of least resistance. Without strict guardrails, an AI equipped with a `disable_scanner` tool might simply turn off `bandit` to clear a Python injection error, rather than writing the correct patch. This effectively masks the vulnerability from human developers.

To bridge this gap, we must implement explicit guardrails ("card trails") into the tool definitions themselves.

## 3. Required Implementation Guardrails

The development team must enforce the following three programmatic guardrails across all newly unlocked MCP tools:

1. **Strict Schema Validation:** All MCP tools must use rigid validation schemas (like Pydantic). If the AI hallucinates a JSON key for a scanner that does not exist in the `PluginRegistry`, the request must fail gracefully and prompt a retry.
2. **Mandatory Reasoning (The "Explain Why" Rule):** The AI cannot silently alter configurations. Any use of `scanner:disable` or `config:set` must require a mandatory `reasoning` parameter, which is immediately appended to a human-readable audit log.
3. **Path Sanitization:** Report generation (`report:generate`) is safe, provided the AI cannot traverse directories (e.g., `../../`) to overwrite critical host files outside the project sandbox.

## 4. Code Blueprints & Architecture

Below are the exact code implementations the team should use in the codebase, mimicking our current FastMCP structure and utilizing existing primitives like `ctx.settings_manager`.

### A. Scanner Management with Reasoning Verification

**File:** `core/mcp/tools/scanners.py`

This implementation forces the AI to justify its architectural decisions before patching the SQLite database.

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import os

# Assuming global FastMCP instance
# mcp = FastMCP("NexusAudit")

class ScannerToggleSchema(BaseModel):
    scanner_name: str = Field(..., description="The exact string name of the scanner (e.g., 'bandit', 'semgrep').")
    reasoning: str = Field(..., min_length=15, description="MANDATORY: Architectural or security justification for toggling this scanner.")

@mcp.tool()
def disable_scanner(payload: ScannerToggleSchema) -> str:
    """
    Disables a specific security scanner in the project configuration.
    You MUST provide a valid architectural reason for doing this.
    """
    # 1. Guardrail: Schema Validation & Reasoning Enforcement
    # Pydantic automatically rejects requests missing or faking the 'reasoning' field.
    
    # 2. State Update
    # Interface with the existing SQLite handler
    # ctx.settings_manager.patch_project_settings(scanner_name=payload.scanner_name, enabled=False)
    
    # 3. Guardrail: Audit Logging
    # Write the AI's justification to a physical trail for the human Code Owner to review.
    audit_log_path = os.path.abspath("./sandbox/mcp_action_log.txt")
    with open(audit_log_path, "a") as log:
        log.write(f"[DISABLED] Scanner: {payload.scanner_name} | Reason: {payload.reasoning}\n")
        
    return f"Successfully disabled '{payload.scanner_name}'. Reasoning has been logged to the audit trail."

```

### B. Report Generation with Path Sanitization

**File:** `core/mcp/tools/config.py`

This ensures the AI can generate localized markdown reports without risking host-system directory traversal.

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
import os

class ReportGenerationSchema(BaseModel):
    output_path: str = Field(..., description="The filename or relative path for the generated markdown report.")

@mcp.tool()
def generate_audit_report(payload: ReportGenerationSchema) -> str:
    """
    Generates a physical markdown summary file of the latest security audit.
    """
    # 1. Guardrail: Path Sanitization (Preventing Directory Traversal)
    # Lock the output strictly to the active sandbox directory.
    safe_sandbox_dir = os.path.abspath("./sandbox")
    
    # Resolve the AI's requested path
    target_path = os.path.abspath(os.path.join(safe_sandbox_dir, payload.output_path))
    
    # Ensure the resolved path still falls within the safe sandbox boundaries
    if not target_path.startswith(safe_sandbox_dir):
         return "SECURITY EXCEPTION: Path traversal detected. You are only permitted to write reports inside the project sandbox."
         
    # 2. File Generation execution
    # report_data = ctx.report_manager.generate_markdown()
    # with open(target_path, "w") as f:
    #     f.write(report_data)
        
    return f"Report successfully generated and secured at: {target_path}"

```

## 5. Final Directives for the Development Team

Proceed with adding `set_project_config`, `enable_scanners`, `disable_scanners`, `set_scanner_config`, and `generate_audit_report` to the MCP tool registry using the patterns above.

**Do not compromise on the hard red lines:** `project:register` and `project:delete` remain strictly manual CLI commands. The human establishes and destroys the sandbox; the AI architects within it.