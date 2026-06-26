import sys
import logging
import signal
import asyncio
from fastmcp import FastMCP

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Force all logging to stderr to prevent stdout corruption
logging.basicConfig(
    stream=sys.stderr, 
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mcp")

# Silence noisy libraries
for noisy_lib in ["httpx", "httpcore", "urllib3", "anyio"]:
    logging.getLogger(noisy_lib).setLevel(logging.WARNING)

async def _handle_sigterm():
    """Flush in-progress work and exit cleanly on SIGTERM."""
    logger.info("SIGTERM received — flushing and exiting")
    await asyncio.sleep(0)
    raise SystemExit(0)

mcp = FastMCP("nexus_audit")

# Import and register tools
from core.mcp.tools import info, audit, findings, scanners, config

info.register(mcp)
audit.register(mcp)
findings.register(mcp)
scanners.register(mcp)
config.register(mcp)

def run():
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(_handle_sigterm()))
    except NotImplementedError:
        pass # Windows does not support add_signal_handler for SIGTERM
    mcp.run()

if __name__ == "__main__":
    run()
