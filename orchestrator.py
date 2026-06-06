import asyncio
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from core.models import Job, Settings, Finding, finding_to_dict, ScanResult
from core.events import EventBus, EventType
from core.atomic import write_json
from core.registry import PluginRegistry
from plugins.base import BaseScanner

UTC = timezone.utc



class Orchestrator:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._current_job: Optional[Job] = None
        self._current_task: Optional[asyncio.Task] = None

    @property
    def current_job(self) -> Optional[Job]:
        return self._current_job

    async def cancel_run(self) -> Job:
        if not self._current_job or self._current_job.state != "running" or self._current_task is None:
            raise RuntimeError("No running job to cancel")

        self._current_task.cancel()
        try:
            await self._current_task
        except asyncio.CancelledError:
            pass

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
        asyncio.create_task(self.bus.publish(EventType.STATUS, {"state": "running", "job_id": job.id}))
        self._current_task = asyncio.create_task(self._run_job(job, settings))
        return job

    async def _run_job(self, job: Job, settings: Settings):
        try:
            await self.run(job, settings)
        except asyncio.CancelledError:
            job.state = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            await self.bus.publish(EventType.STATUS, {"state": "cancelled", "job_id": job.id})
        except Exception as e:
            await self.bus.publish(EventType.LOG, {"level": "error", "message": f"Job failed: {str(e)}"})
            job.state = "failed"
            await self.bus.publish(EventType.STATUS, {"state": "failed", "job_id": job.id})
        finally:
            if self._current_job == job:
                # We don't clear _current_job so status can still be queried
                pass

    async def run(self, job: Job, settings: Settings):
        """
        Phase 3: Run scanners in parallel per Section 4.3 of TECHNICAL_SPEC.md
        Loads registry, runs enabled scanners, collects findings, writes audit_data_complete.json
        """
        try:
            await self.bus.publish(EventType.LOG, {"level": "info", "message": "Loading scanner plugins..."})
            
            # Phase 3: Load scanner registry
            registry = PluginRegistry(Path("plugins"))
            registry.load()
            
            # Prepare scanner tasks
            scanner_tasks = []
            working_path = Path(settings.project_path)
            
            await self.bus.publish(EventType.LOG, {"level": "info", "message": f"Scanning {working_path}..."})
            
            for name, enabled in settings.scanners.items():
                if not enabled:
                    continue
                    
                cls = registry.get(name)
                if cls is None:
                    await self.bus.publish(EventType.LOG, {"level": "warning", "message": f"Scanner not found: {name}"})
                    continue
                
                config = settings.scanner_configs.get(name, {})
                config["_force_rescan"] = settings.force_rescan
                
                # Create scanner task
                task = asyncio.create_task(
                    self._run_single_scanner(cls, working_path, config, name)
                )
                scanner_tasks.append((name, task))
            
            if not scanner_tasks:
                await self.bus.publish(EventType.LOG, {"level": "warning", "message": "No enabled scanners found"})
                scanner_findings = []
            else:
                # Run all scanners in parallel
                results = await asyncio.gather(
                    *[t for _, t in scanner_tasks], return_exceptions=True
                )
                
                scanner_findings: list[Finding] = []
                for i, result in enumerate(results):
                    scanner_name = scanner_tasks[i][0]
                    if isinstance(result, list):
                        scanner_findings.extend(result)
                        job.scan_results.append(ScanResult(
                            scanner=scanner_name,
                            started_at=datetime.now(UTC),
                            finished_at=datetime.now(UTC),
                            findings=result
                        ))
                        await self.bus.publish(EventType.LOG, {
                            "level": "info",
                            "message": f"Scanner '{scanner_name}' found {len(result)} findings"
                        })
                    elif isinstance(result, Exception):
                        await self.bus.publish(EventType.LOG, {
                            "level": "error",
                            "message": f"Scanner '{scanner_name}' failed: {str(result)}"
                        })
            
            # Build and write audit_data_complete.json
            audit_data = {
                "metadata": {
                    "job_id": job.id,
                    "project_path": str(job.project_path),
                    "started_at": job.started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat(),
                    "total_findings": len(scanner_findings),
                    "total_violations": len([f for f in scanner_findings if f.category.value == "architecture"]),
                    "git_context": job.git_context or {}
                },
                "findings": [finding_to_dict(f) for f in scanner_findings],
                "apps": {},
                "coupling_matrix": {},
                "dna": {"modules": []},
                "config_health": {},
                "dependencies": [],
                "recommendations": [],
                "change_summary": {},
                "rules_summary": {}
            }
            
            await write_json(Path("audit_data_complete.json"), audit_data)
            await self.bus.publish(EventType.LOG, {
                "level": "info",
                "message": f"Wrote audit_data_complete.json with {len(scanner_findings)} findings"
            })
            
            # Mark job complete
            job.state = "completed"
            job.finished_at = datetime.now(UTC)
            await self.bus.publish(EventType.STATUS, {"state": "completed", "job_id": job.id})
            
        except Exception as e:
            await self.bus.publish(EventType.LOG, {"level": "error", "message": f"Audit failed: {str(e)}"})
            job.state = "failed"
            job.finished_at = datetime.now(UTC)
            await self.bus.publish(EventType.STATUS, {"state": "failed", "job_id": job.id})
            raise
    
    async def _run_single_scanner(self, scanner_cls: type[BaseScanner], target: Path, config: dict, name: str) -> list[Finding]:
        """
        Run a single scanner with timeout and error handling
        """
        try:
            scanner_instance = scanner_cls()
            
            # Update progress
            await self.bus.publish(EventType.PROGRESS, {
                "scanner": name,
                "percent": 10,
                "file": str(target)
            })
            
            # Run scanner with timeout
            findings = await asyncio.wait_for(
                scanner_instance.scan(target, config, self.bus),
                timeout=scanner_cls.timeout
            )
            
            # Complete progress
            await self.bus.publish(EventType.PROGRESS, {
                "scanner": name,
                "percent": 100,
                "file": str(target)
            })
            
            return findings if findings else []
        except asyncio.TimeoutError:
            await self.bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Scanner '{name}' timed out after {scanner_cls.timeout}s"
            })
            return []
        except Exception as e:
            await self.bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Scanner '{name}' error: {str(e)}"
            })
            return []

