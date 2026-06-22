import asyncio
from core.mcp.server import mcp
async def list_t():
    tools = await mcp.list_tools()
    print([t.name for t in tools])
asyncio.run(list_t())
