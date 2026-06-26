from pathlib import Path
from fastmcp import FastMCP
from typing import List

def register(mcp: FastMCP):
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

    @mcp.tool()
    async def list_projects() -> dict:
        """List all projects registered in Nexus Audit."""
        from core.primitives.settings import SettingsManager
        try:
            workspace = await SettingsManager().load_workspace()
            projects = []
            for pid, proj in workspace.projects.items():
                projects.append({
                    "id": proj.id,
                    "name": proj.name,
                    "path": proj.path
                })
            return {"projects": projects, "count": len(projects)}
        except Exception as e:
            return {"error": str(e)}
