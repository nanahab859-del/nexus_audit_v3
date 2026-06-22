import os
from pathlib import Path
from fastmcp import FastMCP
from core.mcp.schemas import ScannerToggleInput, ScannerConfigInput, resolve_project_id
from core.primitives.settings import SettingsManager
from core.mcp.locks import project_lock

def log_action(action: str, target: str, reason: str):
    log_path = Path.home() / ".nexus_audit" / "mcp_action_log.txt"
    try:
        with open(log_path, "a") as f:
            f.write(f"[{action}] Target: {target} | Reason: {reason}\n")
    except Exception as e:
        import logging
        logging.error(f"Failed to write MCP action log: {e}")

def register(mcp: FastMCP):
    @mcp.tool()
    async def enable_scanners(input: ScannerToggleInput) -> str:
        """
        Enables one or more security scanners in the project configuration.
        You MUST provide a valid architectural reason for doing this.
        """
        try:
            project_id = await resolve_project_id(input.project_path)
            async with project_lock(project_id):
                sm = SettingsManager()
                patch = {"scanners": {name: True for name in input.scanner_names}}
                await sm.patch_project_settings(project_id, patch)
                
            log_action("ENABLE_SCANNERS", ", ".join(input.scanner_names), input.reasoning)
            return f"Successfully enabled scanners: {', '.join(input.scanner_names)}. Reasoning has been logged to the audit trail."
        except Exception as e:
            return f"Error enabling scanners: {e}"

    @mcp.tool()
    async def disable_scanners(input: ScannerToggleInput) -> str:
        """
        Disables one or more security scanners in the project configuration.
        You MUST provide a valid architectural reason for doing this.
        """
        try:
            project_id = await resolve_project_id(input.project_path)
            async with project_lock(project_id):
                sm = SettingsManager()
                patch = {"scanners": {name: False for name in input.scanner_names}}
                await sm.patch_project_settings(project_id, patch)
                
            log_action("DISABLE_SCANNERS", ", ".join(input.scanner_names), input.reasoning)
            return f"Successfully disabled scanners: {', '.join(input.scanner_names)}. Reasoning has been logged to the audit trail."
        except Exception as e:
            return f"Error disabling scanners: {e}"

    @mcp.tool()
    async def set_scanner_config(input: ScannerConfigInput) -> str:
        """
        Configures the strictness level for a specific scanner.
        You MUST provide a valid architectural reason for changing this config.
        """
        try:
            project_id = await resolve_project_id(input.project_path)
            async with project_lock(project_id):
                sm = SettingsManager()
                patch = {"scanner_configs": {input.scanner_name: {"strictness": input.strictness}}}
                await sm.patch_project_settings(project_id, patch)
                
            log_action("SET_SCANNER_CONFIG", f"{input.scanner_name} (strictness={input.strictness})", input.reasoning)
            return f"Successfully updated config for '{input.scanner_name}'. Reasoning has been logged to the audit trail."
        except Exception as e:
            return f"Error setting scanner config: {e}"
