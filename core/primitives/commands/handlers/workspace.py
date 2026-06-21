from core.primitives.commands.context import READONLY, ADMIN
from core.primitives.commands.handlers._utils import resolve_project_id


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="workspace:status",
        description="Show registered project count and active project.",
        usage="workspace:status",
        handler=_handle_status,
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="workspace:active",
        description="Set the active project by ID or 8-char prefix.",
        usage="workspace:active <project_id>",
        handler=_handle_active,
        required_privilege=ADMIN,
        parser=CommandParser("workspace:active").add_argument("project_id"),
    ))


async def _handle_status(ctx, params):
    ctx.write(f"Projects : {len(ctx.workspace.projects)}")
    ctx.write(f"Active   : {ctx.active_project.name if ctx.active_project else 'None'}")


async def _handle_active(ctx, params):
    # resolve_project_id handles exact UUID, 8-char prefix, and ambiguous prefix
    full_pid = resolve_project_id(ctx, params["project_id"])
    if full_pid is None:
        return   # error already written by resolve_project_id

    await ctx.settings_manager.set_active_project(full_pid)
    ctx.workspace.active_project_id = full_pid
    ctx.active_project = await ctx.settings_manager.load_project(full_pid)
    ctx.mark_dirty()
    proj_name = ctx.workspace.projects[full_pid].name
    ctx.write(f"Active project set to '{proj_name}' ({full_pid[:8]}).")
