from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.primitives.models import Workspace, Project
    from core.primitives.settings import SettingsManager

# Privilege levels — single source of truth
READONLY = 0
OPERATOR = 1
ADMIN    = 2
SYSTEM   = 3

PRIV_NAMES = {
    READONLY: "READONLY",
    OPERATOR: "OPERATOR",
    ADMIN:    "ADMIN",
    SYSTEM:   "SYSTEM",
}


@dataclass
class CommandContext:
    workspace:        "Workspace"
    settings_manager: "SettingsManager"
    active_project:   Optional["Project"] = None
    stdout_buffer:    List[str] = field(default_factory=list)
    has_error:        bool = False
    privilege_level:  int  = OPERATOR
    workspace_dirty:  bool = False   # set True by mutating handlers so CLI knows to resync
    exit_requested:   bool = False   # set True by the exit handler
    orchestrator:     Optional[Any] = None   # injected Orchestrator instance

    # ── Output accumulation — NO side effects, NO terminal I/O ────────────────

    def write(self, text: str) -> None:
        """Append a line to the output buffer."""
        self.stdout_buffer.append(str(text))

    def write_error(self, text: str) -> None:
        """Append an error line and set the error flag."""
        self.has_error = True
        self.stdout_buffer.append(f"[ERROR] {text}")

    def write_json(self, data: Any) -> None:
        """Serialise data to JSON and append to buffer."""
        import json
        self.stdout_buffer.append(json.dumps(data, indent=2, default=str))

    def mark_dirty(self) -> None:
        """Call from any handler that mutates workspace or active project."""
        self.workspace_dirty = True
