"""Job orchestrator — manages job lifecycle and runs scans."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.atomic import write_json
from core.events import bus
from core.models import Finding, Job, Severity, Category, ScanResult, Settings

UTC = timezone.utc


class ConflictError(Exception):
    """Raised when a job is already running."""
    pass


class Orchestrator:
    """Manages job lifecycle — start, run, cancel, track state."""

    def __init__(self) -> None:
        self._current_job: Job | None = None
        self._current_task: asyncio.Task | None = None

    async def start_job(self, project_path: Path, settings: Settings) -> Job:
        """
        Start a new audit job.
        Raises ConflictError if a job is already running (→ HTTP 409).
        """
        if self._current_job is not None and self._current_job.state == "running":
            raise ConflictError("A job is already running")

        job = Job(
            project_path=project_path,
            started_at=datetime.now(UTC),
        )
        self._current_job = job

        await bus.publish_status("running", job.id)

        # Launch the job in background
        self._current_task = asyncio.create_task(self._run_job(job, settings))

        return job

    async def cancel_job(self) -> None:
        """Cancel the running job. No-op if nothing is running."""
        if self._current_task is None:
            return

        self._current_task.cancel()
        try:
            await self._current_task
        except asyncio.CancelledError:
            pass

        if self._current_job:
            self._current_job.state = "cancelled"
            self._current_job.finished_at = datetime.now(UTC)
            await bus.publish_status("cancelled", self._current_job.id)

    def current_job(self) -> Job | None:
        """Return the current job."""
        return self._current_job

    def status(self) -> dict:
        """Return status dict for GET /api/status."""
        if self._current_job is None:
            return {"state": "idle", "job_id": None}
        return {"state": self._current_job.state, "job_id": self._current_job.id}

    async def _run_job(self, job: Job, settings: Settings) -> None:
        """
        Run a job (stub for Phase 2, real scanners in Phase 3).
        Simulates a scan with progress events.
        """
        try:
            # Stage 1: initialization
            await asyncio.sleep(1)
            await bus.publish_log("info", "Starting audit...")
            await bus.publish_progress("stub", 0, "")

            # Stage 2: scanning
            await asyncio.sleep(2)
            await bus.publish_progress("stub", 50, "app.py")

            # Emit a fake finding
            finding = Finding(
                scanner="stub",
                file="app.py",
                line=1,
                column=1,
                severity=Severity.INFO,
                category=Category.SECURITY,
                title="Stub finding",
                description="This is a placeholder finding from the Phase 2 stub",
            )
            scan_result = ScanResult(
                scanner="stub",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                findings=[finding],
            )
            job.scan_results.append(scan_result)

            await bus.publish_finding(
                {
                    "id": finding.id,
                    "scanner": finding.scanner,
                    "file": finding.file,
                    "line": finding.line,
                    "column": finding.column,
                    "severity": finding.severity.name,
                    "category": finding.category.value,
                    "title": finding.title,
                    "description": finding.description,
                }
            )

            # Stage 3: completion
            await asyncio.sleep(1)
            await bus.publish_progress("stub", 100, "")

            job.state = "completed"
            job.finished_at = datetime.now(UTC)
            await bus.publish_status("completed", job.id)

            # Write results
            await self._write_job_results(job)

        except asyncio.CancelledError:
            job.state = "cancelled"
            job.finished_at = datetime.now(UTC)
            raise
        except Exception as e:
            job.state = "failed"
            job.finished_at = datetime.now(UTC)
            await bus.publish_status("failed", job.id)
            print(f"Job failed: {e}", file=sys.stderr)

    async def _write_job_results(self, job: Job) -> None:
        """Write job results to audit_data_complete.json and audit_history/."""
        # Prepare result data
        result_data = {
            "job_id": job.id,
            "project_path": str(job.project_path),
            "started_at": job.started_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "state": job.state,
            "scan_results": [
                {
                    "scanner": sr.scanner,
                    "started_at": sr.started_at.isoformat(),
                    "finished_at": sr.finished_at.isoformat() if sr.finished_at else None,
                    "findings": [
                        {
                            "id": f.id,
                            "scanner": f.scanner,
                            "file": f.file,
                            "line": f.line,
                            "column": f.column,
                            "severity": f.severity.name,
                            "category": f.category.value,
                            "title": f.title,
                            "description": f.description,
                            "suggestion": f.suggestion,
                            "cwe": f.cwe,
                            "cvss_score": f.cvss_score,
                        }
                        for f in sr.findings
                    ],
                    "error": sr.error,
                }
                for sr in job.scan_results
            ],
        }

        # Write to audit_data_complete.json
        await write_json(Path("audit_data_complete.json"), result_data)

        # Write to audit_history/{timestamp}.json
        history_dir = Path("audit_history")
        history_dir.mkdir(exist_ok=True)
        timestamp = job.started_at.isoformat().replace(":", "-")
        await write_json(history_dir / f"{timestamp}.json", result_data)
