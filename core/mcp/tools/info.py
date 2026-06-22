from fastmcp import FastMCP

def register(mcp: FastMCP):
    @mcp.tool()
    def get_server_info() -> str:
        """Returns information about the Nexus Audit MCP Server."""
        return "Nexus Audit MCP Server v0.1.0"
