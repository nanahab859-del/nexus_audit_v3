"""Run the aiohttp server for nexus_audit_v3."""

import asyncio
import logging
from pathlib import Path

from aiohttp import web

from orchestrator import Orchestrator
from api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Start the server."""
    # Initialize orchestrator
    settings_path = Path("settings.json")
    orchestrator = Orchestrator()
    
    # Create app
    app = create_app(orchestrator, settings_path=settings_path, port=8421)
    
    # Start server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8422, reuse_address=True)
    await site.start()
    
    logger.info("=" * 60)
    logger.info("Server started at http://127.0.0.1:8422")
    logger.info("=" * 60)
    
    try:
        await asyncio.sleep(3600 * 24)  # Keep running for 24 hours
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
