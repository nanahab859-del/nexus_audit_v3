import asyncio
import logging
import aiofiles
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from core.primitives.events import EventBus, EventType
from core.primitives.atomic import write_json

logger = logging.getLogger(__name__)

class AuditLogger:
    def __init__(self, job_id: str, bus: EventBus, output_dir: Path):
        self._job_id = job_id
        self._bus = bus
        self._output_dir = output_dir
        self._log_path = output_dir / "audit.log"
        self._findings_path = output_dir / "findings.json"
        self._findings_buffer: List[dict] = []
        self._tokens: List[str] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._io_failed: bool = False
        self._io_failure_reported: bool = False

    async def start(self) -> None:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._report_io_failure(e)
            return
        
        token_log = self._bus.subscribe(EventType.LOG, self._handle_log)
        token_finding = self._bus.subscribe(EventType.FINDING, self._handle_finding)
        self._tokens = [token_log, token_finding]
        
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        await self._flush_findings()
        
        for token in self._tokens:
            self._bus.unsubscribe(token)

    async def _handle_log(self, event):
        if self._io_failed:
            return
        
        try:
            timestamp = event.timestamp.isoformat()
            level = event.payload.get("level", "INFO").upper()
            message = event.payload.get("message", "")
            
            async with aiofiles.open(self._log_path, mode="a") as f:
                await f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception as e:
            self._report_io_failure(e)

    async def _handle_finding(self, event):
        self._findings_buffer.append(event.payload.get("finding"))
        if len(self._findings_buffer) >= 50:
            await self._flush_findings()

    async def _periodic_flush(self):
        try:
            while True:
                await asyncio.sleep(5)
                await self._flush_findings()
        except asyncio.CancelledError:
            pass

    async def _flush_findings(self):
        if self._io_failed or not self._findings_buffer:
            return
            
        try:
            # Atomic overwrite of findings.json
            await write_json(self._findings_path, self._findings_buffer, indent=4)
        except Exception as e:
            self._report_io_failure(e)

    def _report_io_failure(self, e: Exception):
        if not self._io_failure_reported:
            logger.critical(f"AuditLogger I/O failure for job {self._job_id}: {e}")
            self._io_failure_reported = True
        self._io_failed = True
