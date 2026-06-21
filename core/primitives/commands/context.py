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
    workspace_dirty:  bool = False
    exit_requested:   bool = False
    orchestrator:     Optional[Any] = None

    # ── Buffered output (rendered by CLI after command returns) ────────────────

    def write(self, text: str) -> None:
        """Append a line to the output buffer. Rendered after command returns."""
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

    # ── Live / streaming output (bypasses buffer for real-time display) ────────

    def write_live(self, text: str) -> None:
        """
        Write immediately to the terminal AND to the buffer.

        Use ONLY for long-running streaming commands (log:stream, audit:run
        --follow) where the handler never returns until cancelled. Normal
        commands must use write() so the CLI controls rendering timing.
        """
        import click
        self.stdout_buffer.append(str(text))
        click.echo(str(text))

    def write_live_error(self, text: str) -> None:
        """Live write for error lines in streaming contexts."""
        import click
        self.has_error = True
        line = f"[ERROR] {text}"
        self.stdout_buffer.append(line)
        click.secho(line, fg="red", bold=True)
