import json
from pathlib import Path
from typing import List
from fastmcp import FastMCP
from core.mcp.security import _assert_safe_path

def register(mcp: FastMCP):
    @mcp.tool()
    def get_finding_detail(project_id: str, job_id: str, fingerprint: str) -> dict:
        """Reads the detail of a specific finding from audit_data_complete.json."""
        try:
            complete_path = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs" / job_id / "audit_data_complete.json"))
            if not complete_path.exists():
                return {"error": "Job data not found"}
            with open(complete_path, "r") as f:
                data = json.load(f)
            for finding in data.get("findings", []):
                if finding.get("fingerprint") == fingerprint:
                    return finding
            return {"error": "Finding not found"}
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    def list_findings(project_id: str, job_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """Lists findings for a given job, capped at 100 per call."""
        limit = min(limit, 100)
        try:
            complete_path = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs" / job_id / "audit_data_complete.json"))
            if not complete_path.exists():
                return []
            with open(complete_path, "r") as f:
                data = json.load(f)
            findings = data.get("findings", [])
            return findings[offset:offset+limit]
        except Exception:
            return []

    @mcp.tool()
    def get_file_context(project_id: str, job_id: str, file: str) -> List[dict]:
        """Returns the snippet of code for the given file from findings context."""
        try:
            complete_path = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs" / job_id / "audit_data_complete.json"))
            if not complete_path.exists():
                return []
            with open(complete_path, "r") as f:
                data = json.load(f)
            
            context = []
            for finding in data.get("findings", []):
                if finding.get("file") == file:
                    context.append({
                        "line": finding.get("line"),
                        "snippet": finding.get("snippet"),
                        "rule_id": finding.get("rule_id"),
                        "severity": finding.get("severity")
                    })
            return context
        except Exception:
            return []

    # Explicitly deferred tools
    @mcp.tool()
    def get_fix_queue(project_id: str) -> dict:
        """DEFERRED: Will return the fix queue for the project."""
        return {"status": "deferred"}

    @mcp.tool()
    def get_trend(project_id: str) -> dict:
        """DEFERRED: Will return the score trend for the project."""
        return {"status": "deferred"}

    @mcp.tool()
    def diff_runs(project_id: str, run_a: str, run_b: str) -> dict:
        """DEFERRED: Will return the diff between two runs."""
        return {"status": "deferred"}
