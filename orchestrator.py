import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
from core.models import Job, Settings
from core.events import EventBus, EventType

class Orchestrator:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._current_job: Optional[Job] = None
        self._current_task: Optional[asyncio.Task] = None

    @property
    def current_job(self) -> Optional[Job]:
        return self._current_job

    def start_run(self, settings: Settings) -> Job:
        if self._current_job and self._current_job.state == "running":
            raise RuntimeError("Job already running")
            
        job = Job(
            id=str(uuid.uuid4()),
            project_path=settings.project_path,
            started_at=datetime.now(timezone.utc),
            state="running"
        )
        self._current_job = job
        self._current_task = asyncio.create_task(self._run_job(job, settings))
        return job

    async def _run_job(self, job: Job, settings: Settings):
        try:
            await self.run(job, settings)
        except Exception as e:
            await self.bus.publish(EventType.LOG, {"level": "error", "message": f"Job failed: {str(e)}"})
            job.state = "failed"
            await self.bus.publish(EventType.STATUS, {"state": "failed", "job_id": job.id})
        finally:
            if self._current_job == job:
                # We don't clear _current_job so status can still be queried
                pass

    async def run(self, job: Job, settings: Settings):
        await self.bus.publish(EventType.LOG, {"level": "info", "message": "Starting job..."})
        
        for i in range(0, 101, 20):
            await asyncio.sleep(0.1) # Faster for testing
            await self.bus.publish(EventType.PROGRESS, {"scanner": "stub", "percent": i, "file": f"file_{i}.py"})
            
        await self.bus.publish(EventType.LOG, {"level": "info", "message": "Job complete."})
        job.state = "completed"
        job.finished_at = datetime.now(timezone.utc)
        await self.bus.publish(EventType.STATUS, {"state": "completed", "job_id": job.id})
