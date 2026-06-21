# Shared utilities for command handlers
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.primitives.commands.context import CommandContext


def resolve_project_id(ctx: "CommandContext", prefix: str) -> Optional[str]:
    """
    Resolve a full project UUID from a prefix or exact ID.

    project:list shows only pid[:8]. This function finds the full UUID
    so commands that accept a short prefix work correctly.

    Returns the full UUID string, or None if not found or ambiguous.
    Writes an appropriate error to ctx in both failure cases.
    """
    projects = ctx.workspace.projects

    # Exact match first (handles full UUIDs)
    if prefix in projects:
        return prefix

    # Prefix match
    matches = [pid for pid in projects if pid.startswith(prefix)]

    if len(matches) == 1:
        return matches[0]

    if len(matches) == 0:
        ctx.write_error(
            f"Project '{prefix}' is not registered. "
            "Run 'project:list' to see registered projects."
        )
        return None

    # More than one match — ambiguous prefix
    ctx.write_error(
        f"Prefix '{prefix}' matches {len(matches)} projects. "
        "Use more characters to disambiguate:"
    )
    for pid in matches:
        proj = projects[pid]
        ctx.write(f"  {pid[:12]}  {proj.name}")
    return None
