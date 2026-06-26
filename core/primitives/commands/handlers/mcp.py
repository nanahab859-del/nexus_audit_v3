import os
import json
from pathlib import Path
from core.primitives.commands.context import READONLY, ADMIN
import logging

logger = logging.getLogger(__name__)

def register(registry) -> None:
    from core.primitives.commands.registry import Command

    registry.register(Command(
        name="mcp:config",
        description="Write the agent host config entry for Claude Desktop / Cursor.",
        usage="mcp:config",
        handler=_handle_mcp_config,
        required_privilege=ADMIN,
    ))

    registry.register(Command(
        name="mcp:status",
        description="Check if the MCP server configuration is present.",
        usage="mcp:status",
        handler=_handle_mcp_status,
        required_privilege=READONLY,
    ))

async def _handle_mcp_config(ctx, params):
    ctx.write("Configuring MCP server...")
    
    config_path = Path.home() / ".config" / "claude_desktop_config.json"
    
    mcp_config = {
        "mcpServers": {
            "nexus-audit": {
                "command": "python",
                "args": ["-m", "core.mcp.server"]
            }
        }
    }
    
    try:
        if config_path.exists():
            with open(config_path, "r") as f:
                data = json.load(f)
        else:
            data = {"mcpServers": {}}
            
        data.setdefault("mcpServers", {})["nexus-audit"] = mcp_config["mcpServers"]["nexus-audit"]
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
            
        ctx.write(f"MCP configuration written to {config_path}")
    except Exception as e:
        ctx.write_error(f"Failed to write MCP config: {e}")

async def _handle_mcp_status(ctx, params):
    config_path = Path.home() / ".config" / "claude_desktop_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            if "nexus-audit" in data.get("mcpServers", {}):
                ctx.write("MCP Server configuration is PRESENT.")
                return
        except Exception:
            pass
    ctx.write("MCP Server configuration is NOT present. Run mcp:config to install.")
