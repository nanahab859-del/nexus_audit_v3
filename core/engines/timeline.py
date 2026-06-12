import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict
from dataclasses import replace

from core.primitives.atomic import read_json
from core.primitives.models import Finding, Persistence, ProjectDNA
from core.engines.fix_queue import FixQueue

logger = logging.getLogger(__name__)

async def load_score_history(
    history_dir: Path,
    max_runs: int = 30
) -> dict:
    """
    Load score trends from lightweight audit summary files.
    """
    history_data = {
        "labels": [],
        "fleet_avg": [],
        "apps": {}
    }

    if not history_dir.exists():
        return history_data

    # Gather files
    files = sorted([f for f in history_dir.glob("audit_summary_*.json")], key=lambda x: x.stat().st_mtime, reverse=True)
    
    # Take max_runs
    files = files[:max_runs]
    
    # Read concurrently
    tasks = [read_json(f) for f in files]
    summaries = await asyncio.gather(*tasks)
    
    # Filter valid
    valid_summaries = [s for s in summaries if s and "timestamp" in s and "fleet_average" in s]
    # Reverse to chronological order
    valid_summaries.reverse()
    
    for s in valid_summaries:
        history_data["labels"].append(s["timestamp"])
        history_data["fleet_avg"].append(s["fleet_average"])
        
        for app, score in s.get("app_scores", {}).items():
            if app not in history_data["apps"]:
                history_data["apps"][app] = []
            history_data["apps"][app].append(score)
            
    return history_data

async def compute_violation_persistence(
    history_dir: Path,
    current_findings: List[Finding],
    max_runs: int = 5
) -> List[Finding]:
    """
    Tag each current finding with a persistence status.
    """
    if not history_dir.exists():
        results = []
        for f in current_findings:
            results.append(replace(f, persistence=Persistence.NEW))
        return results
        
    # Gather files
    files = sorted([f for f in history_dir.glob("audit_summary_*.json")], key=lambda x: x.stat().st_mtime, reverse=True)
    files = files[:max_runs]
    
    # Read concurrently
    tasks = [read_json(f) for f in files]
    summaries = await asyncio.gather(*tasks)
    
    # Map fingerprint to count
    fp_counts: Dict[str, int] = {}
    for s in summaries:
        if s and "findings" in s:
            for f_data in s["findings"]:
                fp = f_data.get("fingerprint")
                if fp:
                    fp_counts[fp] = fp_counts.get(fp, 0) + 1
                    
    # Tag findings
    results = []
    for f in current_findings:
        fp = FixQueue.fingerprint(f)
        count = fp_counts.get(fp, 0)
        
        if count == 0:
            persistence = Persistence.NEW
        elif count == max_runs:
            persistence = Persistence.PERSISTENT
        else:
            persistence = Persistence.INTERMITTENT
            
        results.append(replace(f, persistence=persistence))
            
    return results
