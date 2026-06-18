from core.primitives.commands.context import READONLY, ADMIN


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
        description="Set the active project by ID.",
        usage="workspace:active <project_id>",
        handler=_handle_active,
        required_privilege=ADMIN,
        parser=CommandParser("workspace:active").add_argument("project_id"),
    ))


async def _handle_status(ctx, params):
    ctx.write(f"Projects : {len(ctx.workspace.projects)}")
    ctx.write(f"Active   : {ctx.active_project.name if ctx.active_project else 'None'}")


async def _handle_active(ctx, params):
    pid = params["project_id"]
    if pid not in ctx.workspace.projects:
        ctx.write_error(f"Project '{pid}' is not registered.")
        return
    await ctx.settings_manager.set_active_project(pid)
    ctx.workspace.active_project_id = pid
    ctx.active_project = await ctx.settings_manager.load_project(pid)
    ctx.mark_dirty()
    ctx.write(f"Active project set to '{pid}'.")
