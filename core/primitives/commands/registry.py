from __future__ import annotations
import shlex
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

from core.primitives.commands.context import CommandContext, READONLY, PRIV_NAMES
from core.primitives.commands.parser import CommandParser

if TYPE_CHECKING:
    from core.primitives.settings import SettingsManager


@dataclass
class Command:
    name:               str
    description:        str
    usage:              str
    handler:            Callable[[CommandContext, Dict[str, Any]], Awaitable[Any]]
    required_privilege: int                    = READONLY
    parser:             Optional[CommandParser] = None
    aliases:            List[str]              = field(default_factory=list)


class CommandRegistry:
    """
    Routes raw input strings to registered command handlers.

    The orchestrator is INJECTED — this class never imports or instantiates it.
    No Click anywhere in this file.
    """

    def __init__(
        self,
        settings_manager: "SettingsManager",
        orchestrator=None,
    ):
        self._commands: Dict[str, Command] = {}
        self._aliases:  Dict[str, str]     = {
            "run":  "audit:run",
            "ls":   "project:list",
            "fix":  "fix:list",
            "quit": "exit",
        }
        self._settings_manager = settings_manager
        self.orchestrator      = orchestrator
        self._register_all()

    # ── Public API ─────────────────────────────────────────────────────────────

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def list_all(self) -> List[Command]:
        return list(self._commands.values())

    def get(self, name: str) -> Optional[Command]:
        resolved = self._aliases.get(name, name)
        return self._commands.get(resolved)

    async def execute(self, input_string: str, context: CommandContext) -> CommandContext:
        # 1. Tokenise
        try:
            tokens = shlex.split(input_string.strip())
        except ValueError as e:
            context.write_error(f"Parse error: {e}")
            return context

        if not tokens:
            return context

        # 2. Resolve command name
        cmd_name = self._aliases.get(tokens[0], tokens[0])
        args     = tokens[1:]

        if cmd_name not in self._commands:
            context.write_error(
                f"Unknown command '{cmd_name}'. Type 'system:help' for available commands."
            )
            return context

        command = self._commands[cmd_name]

        # 3. Privilege check — single authoritative location
        if context.privilege_level < command.required_privilege:
            required = PRIV_NAMES.get(command.required_privilege, str(command.required_privilege))
            context.write_error(f"Access denied: '{cmd_name}' requires {required} privilege.")
            return context

        # 4. Parse arguments
        if command.parser:
            params, err = command.parser.parse(args)
            if err:
                context.write_error(err)
                return context
        else:
            params = {}

        # 5. Dispatch
        try:
            await command.handler(context, params)
        except Exception as e:
            context.write_error(f"Command '{cmd_name}' failed: {e}")

        return context

    # ── Registration ────────────────────────────────────────────────────────────

    def _register_all(self) -> None:
        """
        Import each handler group and call its register() function.
        Adding a new command group = one new file + one line here.
        """
        from core.primitives.commands.handlers import (
            workspace, project, audit, config,
            scanner, fix, report, system, log, ai, index_ext, mcp,
        )
        workspace.register(self)
        project.register(self)
        audit.register(self)
        config.register(self)
        scanner.register(self)
        fix.register(self)
        report.register(self)
        system.register(self)
        log.register(self)
        ai.register(self)
        index_ext.register(self)
        mcp.register(self)
