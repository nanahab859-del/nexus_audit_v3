from __future__ import annotations
from importlib.metadata import version, PackageNotFoundError
from core.primitives.commands.context import PRIV_NAMES, READONLY, ADMIN


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="exit",
        description="Close the Nexus CLI session.",
        usage="exit",
        handler=_handle_exit,
        required_privilege=READONLY,
        aliases=["quit"],
    ))

    registry.register(Command(
        name="system:help",
        description="List all commands or show help for a specific command.",
        usage="system:help [command]",
        handler=_make_help(registry),
        required_privilege=READONLY,
        parser=CommandParser("system:help").add_argument("command", nargs="?", default=None),
    ))

    registry.register(Command(
        name="system:version",
        description="Print the installed package version.",
        usage="system:version",
        handler=_handle_version,
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="system:status",
        description="Show workspace and session status.",
        usage="system:status",
        handler=_handle_status,
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="system:clear",
        description="Clear the output buffer.",
        usage="system:clear",
        handler=_handle_clear,
        required_privilege=READONLY,
    ))


async def _handle_exit(ctx, params):
    ctx.exit_requested = True
    ctx.write("Goodbye.")


def _make_help(registry):
    """Closure so the help handler can read the live registry."""
    async def _handle_help(ctx, params):
        cmd_name = params.get("command")
        if cmd_name:
            cmd = registry.get(cmd_name)
            if not cmd:
                ctx.write_error(f"Unknown command: {cmd_name}")
                return
            ctx.write(f"Usage:    {cmd.usage}")
            ctx.write(f"Requires: {PRIV_NAMES.get(cmd.required_privilege, '?')}")
            ctx.write(f"          {cmd.description}")
        else:
            ctx.write("Available commands:\n")
            for name, cmd in sorted(registry._commands.items()):
                priv = PRIV_NAMES.get(cmd.required_privilege, "?")
                ctx.write(f"  {name:<26} [{priv:<8}]  {cmd.description}")
    return _handle_help


async def _handle_version(ctx, params):
    try:
        v = version("nexus-audit")
    except PackageNotFoundError:
        v = "dev"
    ctx.write(f"Nexus Audit v{v}")


async def _handle_status(ctx, params):
    ctx.write(f"Active project : {ctx.active_project.name if ctx.active_project else 'None'}")
    ctx.write(f"Workspace path : {ctx.settings_manager._workspace_path}")
    ctx.write(f"Privilege      : {PRIV_NAMES.get(ctx.privilege_level, '?')}")


async def _handle_clear(ctx, params):
    ctx.stdout_buffer.clear()
