import os
from pathlib import Path
from fastmcp import FastMCP
from core.mcp.schemas import ProjectConfigInput, ReportGenerationInput, resolve_project_id
from core.primitives.settings import SettingsManager
from core.reports.report_engine import ReportEngine
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
    async def set_project_config(input: ProjectConfigInput) -> str:
        """
        Updates the high-level configuration parameters for the project.
        You MUST provide a valid architectural reason for changing project config.
        """
        try:
            project_id = await resolve_project_id(input.project_path)
            async with project_lock(project_id):
                sm = SettingsManager()
                await sm.patch_project_settings(project_id, input.config_patch)
                
            log_action("SET_PROJECT_CONFIG", f"Project {project_id}", input.reasoning)
            return f"Successfully patched project config. Reasoning has been logged to the audit trail."
        except Exception as e:
            return f"Error setting project config: {e}"

    @mcp.tool()
    async def generate_audit_report(input: ReportGenerationInput) -> str:
        """
        Generates a physical markdown or JSON summary file of the latest security audit.
        """
        try:
            project_id = await resolve_project_id(input.project_path)
            
            # 1. Guardrail: Path Sanitization (Preventing Directory Traversal)
            # Lock the output strictly to the active sandbox's audit_reports directory.
            safe_sandbox_dir = os.path.abspath(str(Path.home() / ".nexus_audit" / "projects" / project_id / "audit_reports"))
            os.makedirs(safe_sandbox_dir, exist_ok=True)
            
            target_path = None
            if input.output_path:
                target_path = os.path.abspath(os.path.join(safe_sandbox_dir, input.output_path))
                if not target_path.startswith(safe_sandbox_dir):
                    return "SECURITY EXCEPTION: Path traversal detected. You are only permitted to write reports inside the project sandbox."

            sm = SettingsManager()
            proj = await sm.load_project(project_id)
            
            engine = ReportEngine(Path.home() / ".nexus_audit" / "projects")
            final_path = await engine.generate(
                project_id=project_id,
                project_name=proj.name,
                fmt=input.format,
                output_path=Path(target_path) if target_path else None
            )
            
            return f"Report successfully generated and secured at: {final_path}"
        except Exception as e:
            return f"Error generating report: {e}"
