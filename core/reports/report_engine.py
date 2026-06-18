"""Report engine - coordinator for generating audit reports."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.primitives.atomic import read_json
from core.reports.markdown_report import generate_markdown_report
from core.reports.json_report import generate_json_report

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("md", "json")


class ReportEngine:
    """
    Finds audit result data and calls the appropriate report generator.

    Works for both the latest job and any historical job by ID.
    Does not require the Job object to be in memory.
    """

    def __init__(self, projects_dir: Path) -> None:
        self._projects_dir = projects_dir

    async def generate(
        self,
        project_id: str,
        project_name: str,
        fmt: str = "md",
        output_path: Optional[Path] = None,
        job_id: Optional[str] = None,
    ) -> Path:
        """
        Generate a report and return the path it was written to.

        Args:
            project_id:   UUID from Project.id
            project_name: Human-readable name for the report header
            fmt:          "md" or "json"
            output_path:  Explicit output path, or None for auto-naming
            job_id:       Specific job to report on, or None for the latest

        Raises:
            FileNotFoundError: No completed audit found.
            ValueError: Unsupported format.
        """
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{fmt}'. "
                f"Supported: {', '.join(SUPPORTED_FORMATS)}"
            )

        result_data, resolved_job_id = await self._load_result(project_id, job_id)

        if output_path is None:
            reports_dir = self._projects_dir / project_id / "audit_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"report_{resolved_job_id[:8]}_{ts}.{fmt}"
            output_path = reports_dir / filename

        if fmt == "md":
            generate_markdown_report(result_data, project_name, output_path)
        else:
            generate_json_report(result_data, project_name, output_path)

        logger.info("Report written: %s", output_path)
        return output_path

    async def list_reports(self, project_id: str) -> list:
        """Return all generated reports, newest first."""
        reports_dir = self._projects_dir / project_id / "audit_reports"
        if not reports_dir.exists():
            return []
        return sorted(
            reports_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    async def _load_result(
        self, project_id: str, job_id: Optional[str]
    ) -> tuple:
        jobs_dir = self._projects_dir / project_id / "jobs"
        if not jobs_dir.exists():
            raise FileNotFoundError(
                f"No jobs directory for project '{project_id}'. "
                "Run 'audit:run' first."
            )

        if job_id:
            job_dir = jobs_dir / job_id
            if not job_dir.exists():
                raise FileNotFoundError(f"Job '{job_id}' not found.")
        else:
            candidates = sorted(jobs_dir.iterdir(), reverse=True)
            job_dir = next(
                (d for d in candidates
                 if d.is_dir() and (d / "audit_data_complete.json").exists()),
                None,
            )
            if job_dir is None:
                raise FileNotFoundError(
                    "No completed audit found. "
                    "Run 'audit:run' and wait for it to finish."
                )

        data = await read_json(job_dir / "audit_data_complete.json")
        if not data:
            raise FileNotFoundError(
                f"audit_data_complete.json empty or missing in {job_dir}"
            )
        return data, job_dir.name
