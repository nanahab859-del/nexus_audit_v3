import json
from pathlib import Path
from typing import List, Dict, Any
from fastmcp import FastMCP
from core.mcp.schemas import (
    FindingDetailInput, ListFindingsInput, FileContextInput,
    FixQueueInput, TrendInput, DiffInput, _assert_safe_path, resolve_project_id
)
from core.mcp.locks import project_lock

def register(mcp: FastMCP):
    @mcp.tool()
    def get_finding_detail(input: FindingDetailInput) -> dict:
        """Reads the detail of a specific finding from audit_data_complete.json."""
        try:
            base_dir = Path.home() / ".nexus_audit" / "projects"
            if not base_dir.exists():
                return {"error": "No projects found"}
                
            for project_dir in base_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                jobs_dir = project_dir / "jobs"
                if not jobs_dir.exists():
                    continue
                for job_dir in jobs_dir.iterdir():
                    complete_path = job_dir / "audit_data_complete.json"
                    if not complete_path.exists():
                        continue
                    with open(complete_path, "r") as f:
                        data = json.load(f)
                    for finding in data.get("findings", []):
                        if finding.get("fingerprint") == input.finding_hash:
                            struct_ctx = finding.get("structural_context")
                            if struct_ctx:
                                ctx_str = json.dumps(struct_ctx)
                                if len(ctx_str) > 4000:
                                    finding["structural_context"] = {"truncated": True, "partial": ctx_str[:4000]}
                                    finding["context_truncated"] = True
                            return finding
            return {"error": "Finding not found"}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_findings(input: ListFindingsInput) -> dict:
        """Lists findings for a given job, filtered and capped at 100 per call."""
        limit = min(input.limit, 100)
        try:
            project_id = await resolve_project_id(input.project_path)
            jobs_dir = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"))
            
            if not jobs_dir.exists():
                return {"total": 0, "returned": 0, "offset": input.offset, "findings": [], "error": "No jobs found"}
            
            job_id = input.run_id
            if not job_id:
                latest_time = 0
                for d in jobs_dir.iterdir():
                    if d.is_dir():
                        mtime = d.stat().st_mtime
                        if mtime > latest_time:
                            latest_time = mtime
                            job_id = d.name
                            
            if not job_id:
                return {"total": 0, "returned": 0, "offset": input.offset, "findings": []}
                
            complete_path = jobs_dir / job_id / "audit_data_complete.json"
            if not complete_path.exists():
                return {"total": 0, "returned": 0, "offset": input.offset, "findings": []}
                
            with open(complete_path, "r") as f:
                data = json.load(f)
                
            findings = data.get("findings", [])
            
            if input.severity:
                findings = [f for f in findings if f.get("severity", "").upper() == input.severity.upper()]
            if input.category:
                findings = [f for f in findings if f.get("category", "").lower() == input.category.lower()]
            if input.status:
                findings = [f for f in findings if f.get("status", "open").lower() == input.status.lower()]
                
            total = len(findings)
            paginated = findings[input.offset : input.offset + limit]
            
            return {
                "total": total,
                "returned": len(paginated),
                "offset": input.offset,
                "findings": paginated
            }
        except Exception as e:
            return {"total": 0, "returned": 0, "offset": input.offset, "findings": [], "error": str(e)}

    @mcp.tool()
    async def get_file_context(input: FileContextInput) -> List[dict]:
        """Returns the snippet of code for the given file from findings context."""
        try:
            project_id = await resolve_project_id(input.project_path)
            jobs_dir = _assert_safe_path(str(Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"))
            
            job_id = None
            latest_time = 0
            if jobs_dir.exists():
                for d in jobs_dir.iterdir():
                    if d.is_dir():
                        mtime = d.stat().st_mtime
                        if mtime > latest_time:
                            latest_time = mtime
                            job_id = d.name
            
            if not job_id:
                return []
                
            complete_path = jobs_dir / job_id / "audit_data_complete.json"
            if not complete_path.exists():
                return []
                
            with open(complete_path, "r") as f:
                data = json.load(f)
            
            context = []
            for finding in data.get("findings", []):
                if finding.get("file") == input.file_path:
                    context.append({
                        "line": finding.get("line"),
                        "snippet": finding.get("snippet"),
                        "rule_id": finding.get("rule_id"),
                        "severity": finding.get("severity")
                    })
                    
            return context[:input.limit]
        except Exception:
            return []

    @mcp.tool()
    async def get_fix_queue(input: FixQueueInput) -> dict:
        """Returns the ranked fix queue — findings ordered by severity × age × recurrence."""
        from core.infra.audit_index import get_fix_queue as idx_get_fix_queue
        import datetime
        from datetime import timezone
        try:
            project_id = await resolve_project_id(input.project_path)
            raw_queue = await idx_get_fix_queue(project_id)

            sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            floor_rank = sev_rank.get(input.severity_floor.upper(), 0)
            now = datetime.datetime.now(timezone.utc).timestamp()

            queue = []
            for idx_item, item in enumerate(raw_queue):
                if sev_rank.get(item.get("severity", "").upper(), 0) < floor_rank:
                    continue
                first_ts = item.get("first_seen_ts", now)
                age_days = int((now - first_ts) / 86400)
                queue.append({
                    "rank": idx_item + 1,
                    "finding_hash": item["fingerprint"],
                    "rule_id": item["category"],
                    "severity": item["severity"],
                    "file_path": item["file_path"],
                    "age_days": max(0, age_days),
                    "score_impact": 0.0,
                })

            return {"total": len(queue), "queue": queue[:input.limit]}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_trend(input: TrendInput) -> dict:
        """Returns the score trend for the project."""
        from core.infra.audit_index import get_trend as idx_get_trend
        import datetime
        try:
            project_id = await resolve_project_id(input.project_path)
            raw_trend = await idx_get_trend(project_id, limit=input.last_n_runs)

            runs = []
            for r in reversed(raw_trend):  # oldest first for the trend table
                dt = datetime.datetime.fromtimestamp(
                    r["timestamp"], tz=datetime.timezone.utc
                )
                runs.append({
                    "timestamp": dt.isoformat(),
                    "git_commit": "?",
                    "scores": {
                        "overall": r["score_overall"],
                        "security": r["score_security"],
                        "quality": r["score_quality"],
                    },
                    "counts": {
                        "critical": r["CRITICAL_count"],
                        "high": r["HIGH_count"],
                    },
                })

            return {"runs": runs}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def diff_runs(input: DiffInput) -> dict:
        """Returns the structural diff between two audit runs."""
        from core.infra.audit_index import diff_runs as idx_diff_runs, get_trend as idx_get_trend
        try:
            project_id = await resolve_project_id(input.project_path)
            async with project_lock(project_id):
                # Fetch recent runs for score delta calculation
                recent = await idx_get_trend(project_id, limit=10)
                run_a = next((r for r in recent if r["run_id"] == input.run_id_a), None)
                run_b = next((r for r in recent if r["run_id"] == input.run_id_b), None)

                score_delta: dict = {}
                if run_a and run_b:
                    score_delta = {
                        "overall": run_b["score_overall"] - run_a["score_overall"],
                        "security": run_b["score_security"] - run_a["score_security"],
                        "quality": run_b["score_quality"] - run_a["score_quality"],
                    }

                diff = await idx_diff_runs(
                    project_id,
                    base_run_id=input.run_id_a,
                    head_run_id=input.run_id_b,
                )
                new_findings = diff.get("new", [])
                sev_counts: dict = {}
                for nf in new_findings:
                    sev = nf.get("severity", "UNKNOWN")
                    sev_counts[sev] = sev_counts.get(sev, 0) + 1

                return {
                    "run_id_a": input.run_id_a,
                    "run_id_b": input.run_id_b,
                    "score_delta": score_delta,
                    "new_findings": {
                        "count": len(new_findings),
                        "by_severity": sev_counts,
                    },
                    "resolved_findings": {
                        "count": len(diff.get("resolved", [])),
                    },
                    "coupling_changes": {"added_edges": [], "removed_edges": []},
                    "probable_commit": None,
                }
        except Exception as e:
            return {"error": str(e)}
