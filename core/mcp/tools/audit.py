import json
import asyncio
from pathlib import Path
from fastmcp import FastMCP
from core.mcp.schemas import RunAuditInput, ProjectInput, _assert_safe_path, resolve_project_id
from core.mcp.locks import project_lock
from core.primitives.settings import SettingsManager
from orchestrator import Orchestrator

def register(mcp: FastMCP):
    @mcp.tool()
    async def run_project_audit(input: RunAuditInput) -> dict:
        """Run a new audit for the given project_path. Returns job status."""
        try:
            project_id = await resolve_project_id(input.project_path)
            
            async with project_lock(project_id):
                sm = SettingsManager()
                orch = Orchestrator(sm)
                
                job = await orch.start_job(project_id, fast_mode=input.fast_mode)
                while True:
                    status = orch.status()
                    if status["state"] in ("completed", "failed", "cancelled"):
                        break
                    await asyncio.sleep(1)
                
                # Fetch the latest summary after completion to return structured data
                jobs_dir = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"))
                summary_path = jobs_dir / job.id / "audit_summary.json"
                if summary_path.exists():
                    with open(summary_path, "r") as f:
                        data = json.load(f)
                        return {
                            "run_id": data.get("job_id"),
                            "status": status["state"],
                            "duration_ms": 0, # not easily available without diffing timestamps
                            "scores": {
                                "overall": data.get("fleet_average", 0.0),
                                "security": data.get("app_scores", {}).get("security", 0.0),
                                "quality": data.get("app_scores", {}).get("quality", 0.0)
                            },
                            "counts": {
                                "total": data.get("findings_count", 0),
                                "critical": sum(1 for f in data.get("findings", []) if f.get("severity") == "CRITICAL"),
                                "high": sum(1 for f in data.get("findings", []) if f.get("severity") == "HIGH")
                            }
                        }
                return {"error": f"Audit finished with status: {status['state']} but no summary found."}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_latest_audit_summary(input: ProjectInput) -> dict:
        """Reads the latest audit_summary.json directly for a project."""
        try:
            project_id = await resolve_project_id(input.project_path)
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
        except Exception as e:
            return {"error": str(e)}
