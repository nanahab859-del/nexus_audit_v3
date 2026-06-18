"""
Public API for the command layer.

All consumers import from here.
Do not import from submodules directly — internal structure may change.

Usage:
    from core.primitives.commands import CommandRegistry, CommandContext, READONLY
"""
from core.primitives.commands.context import (
    CommandContext,
    READONLY,
    OPERATOR,
    ADMIN,
    SYSTEM,
    PRIV_NAMES,
)
from core.primitives.commands.registry import Command, CommandRegistry

__all__ = [
    "CommandContext",
    "CommandRegistry",
    "Command",
    "READONLY",
    "OPERATOR",
    "ADMIN",
    "SYSTEM",
    "PRIV_NAMES",
]
