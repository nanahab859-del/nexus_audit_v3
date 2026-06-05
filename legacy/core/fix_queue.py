import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.models import Finding

StatusType = Literal["open", "in_progress", "done", "snoozed"]

@dataclass
class SyncResult:
    reappeared: list[str]     # finding IDs marked done but back in current run
    new_count: int
    resolved_count: int

@dataclass
class StatusEntry:
    status: StatusType
    note: str = ""
    reappeared: bool = False

class FixQueue:
    """
    Tracks status of findings across audit runs.
    """
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._data: dict[str, StatusEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.db_path.exists():
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for finding_id, entry in data.items():
                    self._data[finding_id] = StatusEntry(
                        status=entry.get("status", "open"),
                        note=entry.get("note", ""),
                        reappeared=entry.get("reappeared", False)
                    )
        except Exception:
            pass

    def _save(self) -> None:
        try:
            data = {
                fid: {"status": e.status, "note": e.note, "reappeared": e.reappeared}
                for fid, e in self._data.items()
            }
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_status(self, finding_id: str) -> StatusEntry | None:
        return self._data.get(finding_id)

    def get_all(self) -> dict[str, Any]:
        return {
            fid: {"status": e.status, "note": e.note, "reappeared": e.reappeared}
            for fid, e in self._data.items()
        }

    def update_status(self, finding_id: str, status: StatusType, note: str = "") -> None:
        if finding_id not in self._data:
            self._data[finding_id] = StatusEntry(status=status, note=note)
        else:
            self._data[finding_id].status = status
            self._data[finding_id].note = note
            if status != "done":
                self._data[finding_id].reappeared = False
        self._save()

    def sync(self, current_findings: list[Finding]) -> SyncResult:
        current_ids = {f.id for f in current_findings}
        
        reappeared = []
        new_count = 0
        resolved_count = 0
        
        for fid in current_ids:
            if fid not in self._data:
                self._data[fid] = StatusEntry(status="open")
                new_count += 1
            else:
                entry = self._data[fid]
                if entry.status == "done":
                    entry.status = "open"
                    entry.reappeared = True
                    reappeared.append(fid)
                    
        # Mark open things that are no longer present as done/resolved
        for fid, entry in self._data.items():
            if fid not in current_ids and entry.status in ("open", "in_progress"):
                entry.status = "done"
                entry.note = "Auto-resolved (not found in latest scan)"
                resolved_count += 1
                
        self._save()
        return SyncResult(reappeared=reappeared, new_count=new_count, resolved_count=resolved_count)
