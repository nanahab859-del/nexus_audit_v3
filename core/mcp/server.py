import sys
import logging
from fastmcp import FastMCP

# Force all logging to stderr to prevent stdout corruption
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("mcp")

mcp = FastMCP("nexus_audit")

# Import and register tools
from core.mcp.tools import info, audit, findings

info.register(mcp)
audit.register(mcp)
findings.register(mcp)

if __name__ == "__main__":
    mcp.run()
