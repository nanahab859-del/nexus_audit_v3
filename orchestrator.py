import asyncio
from core.models import Job, Settings
from core.events import EventBus, EventType

class Orchestrator:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def run(self, job: Job, settings: Settings):
        await self.bus.publish(EventType.LOG, {"message": "Starting job..."})
        
        for i in range(0, 101, 20):
            await asyncio.sleep(0.1) # Faster for testing
            await self.bus.publish(EventType.PROGRESS, {"scanner": "stub", "percent": i, "file": f"file_{i}.py"})
            
        await self.bus.publish(EventType.LOG, {"message": "Job complete."})
        await self.bus.publish(EventType.STATUS, {"state": "completed", "job_id": job.id})
