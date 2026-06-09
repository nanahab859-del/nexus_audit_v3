import asyncio
import uuid
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from core.models import Job, Settings, Finding, finding_to_dict, ScanResult
from core.events import EventBus, EventType
from core.atomic import write_json
from core.registry import PluginRegistry
from core.language_detection import detect_languages, is_language_supported
from plugins.base import BaseScanner
from plugins.generic_script_scanner import GenericScriptScanner

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
        Loads registry, detects languages, filters scanners, collects findings, writes audit_data_complete.json
        """
        try:
            await self.bus.publish(EventType.LOG, {"level": "info", "message": "Loading scanner plugins..."})
            
            # Phase 3: Load scanner registry
            registry = PluginRegistry(Path("plugins"))
            registry.load()
            
            # Detect programming languages in target
            working_path = Path(settings.project_path)
            await self.bus.publish(EventType.LOG, {"level": "info", "message": f"Detecting languages in {working_path}..."})
            detected_languages = detect_languages(working_path)
            
            if detected_languages:
                await self.bus.publish(EventType.LOG, {
                    "level": "info",
                    "message": f"Detected languages: {', '.join(sorted(detected_languages))}"
                })
            else:
                await self.bus.publish(EventType.LOG, {
                    "level": "warning",
                    "message": "No recognized source files found. Proceeding anyway..."
                })
            
            # Build file-filter from inclusions / exclusions / extensions
            _file_filter = {
                "inclusions":         list(settings.inclusions or []),
                "exclusions":         list(settings.exclusions or []),
                "enabled_extensions": list(settings.enabled_extensions or []),
            }

            # Load custom scanners from settings.ui.custom_scanners
            custom_scanners: dict[str, GenericScriptScanner] = {}
            for cs_name, cs_meta in ((settings.ui or {}).get("custom_scanners", {})).items():
                custom_scanners[cs_name] = GenericScriptScanner(
                    name=cs_name,
                    executable=cs_meta.get("executable", ""),
                    output_pattern=cs_meta.get("output_pattern"),
                )

            # ── Pre-flight summary ────────────────────────────────────────────
            enabled_names  = [n for n, on in settings.scanners.items() if on]
            disabled_names = [n for n, on in settings.scanners.items() if not on]
            await self.bus.publish(EventType.LOG, {
                "level": "info",
                "message": (
                    f"[PRE-FLIGHT] Scanners enabled ({len(enabled_names)}): "
                    f"{', '.join(enabled_names) or 'none'}  |  "
                    f"Disabled ({len(disabled_names)}): "
                    f"{', '.join(disabled_names) or 'none'}"
                )
            })
            await self.bus.publish(EventType.LOG, {
                "level": "info",
                "message": (
                    f"[PRE-FLIGHT] Target: {settings.project_path or '(not set)'}  |  "
                    f"Extensions: {', '.join(settings.enabled_extensions or ['.py'])}  |  "
                    f"Detected languages: {', '.join(sorted(detected_languages)) if detected_languages else 'unknown'}"
                )
            })

            # Prepare scanner tasks, filtering by language compatibility
            scanner_tasks = []

            for name, enabled in settings.scanners.items():
                if not enabled:
                    await self.bus.publish(EventType.LOG, {
                        "level": "info",
                        "message": f"[SKIPPED] '{name}' is disabled in project settings."
                    })
                    continue

                # Resolve scanner class (registered plugin or custom script)
                if name in custom_scanners:
                    scanner_instance = custom_scanners[name]
                    cls = scanner_instance.__class__
                else:
                    cls = registry.get(name)
                    if cls is None:
                        await self.bus.publish(EventType.LOG, {"level": "warning", "message": f"Scanner not found: {name}"})
                        continue
                    scanner_instance = None  # created inside _run_single_scanner

                # Check language compatibility ("*" means any)
                scanner_langs = getattr(cls, "languages", ["*"])
                if scanner_langs != ["*"] and not is_language_supported(scanner_langs, detected_languages):
                    await self.bus.publish(EventType.LOG, {
                        "level": "info",
                        "message": f"Skipping '{name}' (supports {', '.join(scanner_langs)}, target has {', '.join(sorted(detected_languages)) if detected_languages else 'unknown languages'})"
                    })
                    continue

                # Merge per-scanner config with file filter
                config = dict(settings.scanner_configs.get(name, {}))
                config["_force_rescan"] = settings.force_rescan
                config["_file_filter"]  = _file_filter

                await self.bus.publish(EventType.LOG, {
                    "level": "info",
                    "message": f"Running '{name}' scanner..."
                })

                # Create scanner task
                task = asyncio.create_task(
                    self._run_single_scanner(
                        cls, working_path, config, name,
                        instance=scanner_instance,
                    )
                )
                scanner_tasks.append((name, task))
            
            if not scanner_tasks:
                await self.bus.publish(EventType.LOG, {"level": "warning", "message": "No compatible scanners to run"})
                scanner_findings = []
            else:
                # Run all scanners in parallel
                results = await asyncio.gather(
                    *[t for _, t in scanner_tasks], return_exceptions=True
                )
                
                scanner_findings: list[Finding] = []
                scanner_errors = []  # Track scanner errors for frontend visibility
                
                for i, result in enumerate(results):
                    scanner_name = scanner_tasks[i][0]
                    if isinstance(result, list):
                        # Scanners now handle errors internally and return []
                        job.scan_results.append(ScanResult(
                            scanner=scanner_name,
                            started_at=datetime.now(UTC),
                            finished_at=datetime.now(UTC),
                            findings=result,
                            error=None
                        ))
                        scanner_findings.extend(result)
                        await self.bus.publish(EventType.LOG, {
                            "level": "info",
                            "message": f"Scanner '{scanner_name}' found {len(result)} findings"
                        })
                    elif isinstance(result, Exception):
                        # Unexpected exception (not a missing-tool error, which scanner handles)
                        error_msg = str(result)
                        scanner_errors.append(error_msg)
                        job.scan_results.append(ScanResult(
                            scanner=scanner_name,
                            started_at=datetime.now(UTC),
                            finished_at=datetime.now(UTC),
                            findings=[],
                            error=error_msg
                        ))
                        await self.bus.publish(EventType.LOG, {
                            "level": "error",
                            "message": f"Scanner '{scanner_name}' failed: {error_msg}"
                        })
                
                # Audit completes successfully (even if some scanners unavailable)
                # Frontend will show warning banner for any scanner errors
            
            # Build and write audit_data_complete.json
            await self.bus.publish(EventType.LOG, {
                "level": "info",
                "message": f"[ORCHESTRATOR DEBUG] Collected {len(scanner_findings)} total findings from all scanners"
            })
            
            # Debug: show breakdown
            for sr in job.scan_results:
                await self.bus.publish(EventType.LOG, {
                    "level": "debug",
                    "message": f"[ORCHESTRATOR DEBUG] Scanner '{sr.scanner}': {len(sr.findings)} findings"
                })
            
            audit_data = {
                "metadata": {
                    "job_id": job.id,
                    "project_path": str(job.project_path),
                    "project_name": settings.project_name or "",
                    "project_version": settings.project_version or "",
                    "started_at": job.started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat(),
                    "total_findings": len(scanner_findings),
                    "total_violations": len([f for f in scanner_findings if f.category.value == "architecture"]),
                    "git_context": job.git_context or {},
                    "custom_metadata": settings.custom_metadata or [],
                },
                "findings": [finding_to_dict(f) for f in scanner_findings],
                "scan_results": [
                    {
                        "scanner": sr.scanner,
                        "started_at": sr.started_at.isoformat(),
                        "finished_at": sr.finished_at.isoformat(),
                        "findings": [finding_to_dict(f) for f in sr.findings],
                        "error": sr.error
                    }
                    for sr in job.scan_results
                ],
                "apps": {},
                "coupling_matrix": {},
                "dna": {"modules": []},
                "config_health": {},
                "dependencies": [],
                "recommendations": [],
                "change_summary": {},
                "rules_summary": {}
            }
            
            # Debug: verify data before write
            await self.bus.publish(EventType.LOG, {
                "level": "debug",
                "message": f"[ORCHESTRATOR DEBUG] audit_data findings count: {len(audit_data['findings'])}"
            })
            
            await write_json(Path("audit_data_complete.json"), audit_data)
            
            # Debug: verify file was written
            from core.atomic import read_json
            verify = await read_json(Path("audit_data_complete.json"))
            if verify:
                await self.bus.publish(EventType.LOG, {
                    "level": "info",
                    "message": f"[ORCHESTRATOR DEBUG] ✓ File written and verified: {len(verify.get('findings', []))} findings in file"
                })
            else:
                await self.bus.publish(EventType.LOG, {
                    "level": "error",
                    "message": f"[ORCHESTRATOR DEBUG] ✗ File write FAILED - file is empty or unreadable!"
                })
            
            await self.bus.publish(EventType.LOG, {
                "level": "info",
                "message": f"Wrote audit_data_complete.json with {len(scanner_findings)} findings"
            })
            
            # Mark job complete
            job.state = "completed"
            job.finished_at = datetime.now(UTC)
            await self.bus.publish(EventType.STATUS, {"state": "completed", "job_id": job.id})

            # Fire webhook if configured
            if settings.webhook_url:
                try:
                    import aiohttp
                    payload = {
                        "event":          "audit_complete",
                        "job_id":         job.id,
                        "project_path":   str(job.project_path),
                        "total_findings": len(scanner_findings),
                        "state":          "completed",
                    }
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            settings.webhook_url,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10),
                        )
                    await self.bus.publish(EventType.LOG, {"level": "info", "message": "Webhook notification sent"})
                except Exception as wh_err:
                    await self.bus.publish(EventType.LOG, {"level": "warning", "message": f"Webhook failed: {wh_err}"})
            
        except Exception as e:
            await self.bus.publish(EventType.LOG, {"level": "error", "message": f"Audit failed: {str(e)}"})
            job.state = "failed"
            job.finished_at = datetime.now(UTC)
            await self.bus.publish(EventType.STATUS, {"state": "failed", "job_id": job.id})
            raise
    
    async def _run_single_scanner(
        self,
        scanner_cls: type[BaseScanner],
        target: Path,
        config: dict,
        name: str,
        instance: Optional[BaseScanner] = None,
    ) -> list[Finding]:
        """
        Run a single scanner with timeout and error handling.
        If `instance` is provided (custom scanner), use it directly;
        otherwise instantiate scanner_cls().
        """
        try:
            scanner = instance if instance is not None else scanner_cls()

            await self.bus.publish(EventType.PROGRESS, {
                "scanner": name, "percent": 10, "file": str(target)
            })
            await self.bus.publish(EventType.LOG, {
                "level": "debug",
                "message": f"[SCANNER DEBUG] '{name}' starting scan of {target}..."
            })

            findings = await asyncio.wait_for(
                scanner.scan(target, config, self.bus),
                timeout=scanner_cls.timeout,
            )

            await self.bus.publish(EventType.LOG, {
                "level": "debug",
                "message": f"[SCANNER DEBUG] '{name}' returned {len(findings) if findings else 0} findings"
            })
            await self.bus.publish(EventType.PROGRESS, {
                "scanner": name, "percent": 100, "file": str(target)
            })

            return findings if findings else []

        except asyncio.TimeoutError as exc:
            msg = f"Scanner '{name}' timed out after {scanner_cls.timeout}s"
            await self.bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"[SCANNER ERROR] {msg}"
            })
            raise TimeoutError(msg) from exc
        except Exception as exc:
            msg = f"Scanner '{name}' error: {str(exc)}"
            await self.bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"[SCANNER ERROR] {msg}"
            })
            raise RuntimeError(msg) from exc

