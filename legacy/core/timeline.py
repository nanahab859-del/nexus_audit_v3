from typing import Any
import json
from pathlib import Path

from core.models import Finding

def load_score_history(history_dir: Path, max_runs: int = 30) -> dict[str, Any]:
    """
    Reads audit_history/ to build trend data.
    Returns: {"labels": [...], "apps": {app: [scores]}, "fleet_avg": [...]}
    """
    if not history_dir.exists():
        return {"labels": [], "apps": {}, "fleet_avg": []}
        
    # Get all json files sorted by name (which starts with timestamp)
    history_files = sorted(list(history_dir.glob("*.json")))
    history_files = history_files[-max_runs:]
    
    labels = []
    apps: dict[str, list[float | None]] = {}
    fleet_avg: list[float] = []
    
    for i, file_path in enumerate(history_files):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            meta = data.get("metadata", {})
            labels.append(meta.get("timestamp", file_path.stem))
            
            # Ensure lists are padded if an app is missing in earlier runs
            current_apps = data.get("apps", {})
            for app_name, app_data in current_apps.items():
                if app_name == "fleet_average":
                    continue
                if app_name not in apps:
                    apps[app_name] = [None] * i
                apps[app_name].append(app_data.get("score", 0.0))
                
            # Pad missing apps for this run
            for app_name in apps:
                if app_name not in current_apps:
                    apps[app_name].append(None)
                    
            fleet_avg.append(data.get("fleet_average", 0.0))
            
        except Exception:
            continue
            
    return {
        "labels": labels,
        "apps": apps,
        "fleet_avg": fleet_avg
    }

def compute_violation_persistence(
    history_dir: Path,
    current_findings: list[Finding],
    max_runs: int = 5,
) -> dict[str, str]:
    """
    Returns per-finding-id persistence trend:
    "new" | "persistent" | "intermittent" | "resolved"
    """
    persistence: dict[str, str] = {}
    current_ids = {f.id for f in current_findings}
    
    if not history_dir.exists():
        for fid in current_ids:
            persistence[fid] = "new"
        return persistence
        
    history_files = sorted(list(history_dir.glob("*.json")))[-max_runs:]
    
    # Map finding ID to list of booleans (present in run N)
    history_presence: dict[str, list[bool]] = {fid: [] for fid in current_ids}
    
    for file_path in history_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            past_findings = data.get("findings", [])
            past_ids = {f.get("id") for f in past_findings}
            
            # Record presence for current findings
            for fid in current_ids:
                history_presence[fid].append(fid in past_ids)
                
            # Record presence for past findings not in current
            for fid in past_ids:
                if fid not in history_presence:
                    history_presence[fid] = [False] * (len(history_presence.get(list(history_presence.keys())[0], [])) - 1)
                history_presence[fid].append(True)
                
        except Exception:
            for fid in history_presence:
                history_presence[fid].append(False)
                
    # Evaluate persistence
    for fid, presence in history_presence.items():
        if fid not in current_ids:
            persistence[fid] = "resolved"
        elif not any(presence):
            persistence[fid] = "new"
        elif all(presence):
            persistence[fid] = "persistent"
        else:
            persistence[fid] = "intermittent"
            
    return persistence
