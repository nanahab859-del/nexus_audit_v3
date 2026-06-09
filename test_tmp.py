import asyncio
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from core.events import EventBus, EventType
from core.models import Settings, Category
from orchestrator import Orchestrator

async def run_test():
    bus = EventBus()
    events = []
    async def sub(eid, ev): 
        print(f"EVENT: {ev.type} - {ev.data}")
        events.append(ev)
    bus.subscribe_all(sub)

    orc = Orchestrator(bus)

    from plugins.base import BaseScanner

    class SlowScanner(BaseScanner):
        name = "slow_scanner"
        version = "0"
        languages = ["*"]
        category = Category.QUALITY
        timeout = 999

        async def scan(self, target, config, bus):
            print("SLOW SCANNER STARTED")
            await asyncio.sleep(999)
            return []

    settings = Settings(project_path="/tmp", scanners={"slow_scanner": True})

    with patch("orchestrator.PluginRegistry") as MockReg:
        instance = MockReg.return_value
        instance.get.return_value = SlowScanner
        instance.load.return_value = None
        job = orc.start_run(settings)

    await asyncio.sleep(0.05)
    print("JOB STATE AFTER 0.05s:", job.state)
    cancelled_job = await orc.cancel_run()
    print("JOB STATE AFTER CANCEL:", cancelled_job.state)

if __name__ == "__main__":
    asyncio.run(run_test())
