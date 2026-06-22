import json
import asyncio
from pathlib import Path
from pydantic import BaseModel
from fastmcp import FastMCP
from core.mcp.security import _assert_safe_path
from core.primitives.settings import SettingsManager
from orchestrator import Orchestrator

def register(mcp: FastMCP):
    @mcp.tool()
    async def run_project_audit(project_id: str, fast_mode: bool = False) -> str:
        """Run a new audit for the given project_id. Returns job id or status."""
        sm = SettingsManager()
        orch = Orchestrator(sm)
        try:
            job = await orch.start_job(project_id, fast_mode=fast_mode)
            while True:
                status = orch.status()
                if status["state"] in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(1)
            return f"Audit finished with status: {orch.status()['state']} for job: {job.id}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def get_latest_audit_summary(project_id: str) -> dict:
        """Reads the latest audit_summary.json directly for a project."""
        try:
            jobs_dir = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"))
            if not jobs_dir.exists():
                return {"error": "No jobs found"}
            
            latest_summary = None
            latest_time = 0
            
            for job_dir in jobs_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                summary_path = job_dir / "audit_summary.json"
                if summary_path.exists():
                    mtime = summary_path.stat().st_mtime
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_summary = summary_path
                        
            if latest_summary:
                with open(latest_summary, "r") as f:
                    return json.load(f)
            return {"error": "No valid summary found"}
        except ValueError as e:
            return {"error": str(e)}
