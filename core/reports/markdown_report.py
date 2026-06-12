from pathlib import Path
from typing import Any

from core.primitives.models import Job
from core.scoring_engine import AppScore

def generate_markdown_report(
    job: Job,
    scores: dict[str, AppScore],
    config: dict[str, Any],
    output_path: Path,
) -> None:
    lines = []
    
    # Metadata
    project_name = Path(job.project_path).name if isinstance(job.project_path, str) else job.project_path.name
    lines.append(f"# Nexus Audit Report: {project_name}")
    lines.append(f"**Date**: {job.started_at.isoformat()}")
    if job.git_context:
        lines.append(f"**Commit**: {job.git_context.get('commit')} on {job.git_context.get('branch')}")
    lines.append("")
    
    # Fleet average
    fleet = scores.get("fleet_average")
    if fleet:
        lines.append(f"## Fleet Health: {fleet.score:.1f}/100")
    else:
        lines.append("## Fleet Health: N/A")
    lines.append("")
        
    # App scores
    lines.append("## Application Scores")
    lines.append("| App | Score | Violations | Security (H/M/L) |")
    lines.append("|-----|-------|------------|------------------|")
    
    for app, s in scores.items():
        if app == "fleet_average":
            continue
        v = s.finding_counts.get("violations", 0)
        sh = s.finding_counts.get("security_high", 0)
        sm = s.finding_counts.get("security_medium", 0)
        sl = s.finding_counts.get("security_low", 0)
        hub = " (Hub)" if s.is_hub else ""
        lines.append(f"| {app}{hub} | {s.score:.1f} | {v} | {sh} / {sm} / {sl} |")
        
    lines.append("")
    
    # High severity findings
    lines.append("## Key Findings")
    high_findings = []
    for sr in job.scan_results:
        for finding in sr.findings:
            if finding.severity >= 4 or finding.category.value == "architecture":
                high_findings.append(finding)
                
    if not high_findings:
        lines.append("No critical findings or architectural violations.")
    else:
        for finding in high_findings[:50]:  # Limit to 50
            lines.append(f"### {finding.title}")
            lines.append(f"**{finding.severity.name} | {finding.category.name}**")
            lines.append(f"**Location**: `{finding.file}:{finding.line}`")
            lines.append(f"**Description**: {finding.description}")
            if finding.suggestion:
                lines.append(f"**Suggestion**: {finding.suggestion}")
            lines.append("")
            
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
