from pathlib import Path
from core.primitives.commands.context import READONLY, ADMIN


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="project:register",
        description="Register a local path as an auditable project.",
        usage="project:register --path PATH [--name NAME]",
        handler=_handle_register,
        required_privilege=ADMIN,
        parser=(
            CommandParser("project:register")
            .add_argument("--path", default=".", help="Path to project root")
            .add_argument("--name", default="default", help="Human-readable project name")
        ),
    ))

    registry.register(Command(
        name="project:list",
        description="List all registered projects.",
        usage="project:list",
        handler=_handle_list,
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="project:info",
        description="Show details for a project.",
        usage="project:info [project_id]",
        handler=_handle_info,
        required_privilege=READONLY,
        parser=CommandParser("project:info").add_argument("project_id", nargs="?", default=None),
    ))

    registry.register(Command(
        name="project:delete",
        description="Delete a registered project by ID.",
        usage="project:delete <project_id>",
        handler=_handle_delete,
        required_privilege=ADMIN,
        parser=CommandParser("project:delete").add_argument("project_id"),
    ))

    registry.register(Command(
        name="project:clear",
        description="Delete ALL registered projects (requires --force).",
        usage="project:clear [--force]",
        handler=_handle_clear,
        required_privilege=ADMIN,
        parser=CommandParser("project:clear").add_argument("--force", action="store_true"),
    ))


async def _handle_register(ctx, params):
    path = str(Path(params["path"]).expanduser().resolve())
    name = params["name"]
    await ctx.settings_manager.register_project(name, path)
    ctx.mark_dirty()
    ctx.write(f"Project '{name}' registered at {path}")


async def _handle_list(ctx, params):
    if not ctx.workspace.projects:
        ctx.write("No projects registered.")
        return
    active_id = ctx.workspace.active_project_id
    for pid, proj in ctx.workspace.projects.items():
        marker = " *" if pid == active_id else "  "
        ctx.write(f"{marker} {pid[:8]}  {proj.name:<24}  {proj.path}")


async def _handle_info(ctx, params):
    pid = params.get("project_id") or (ctx.active_project.id if ctx.active_project else None)
    if not pid:
        ctx.write_error("Provide a project_id or set an active project.")
        return
    try:
        proj = await ctx.settings_manager.load_project(pid)
    except FileNotFoundError:
        ctx.write_error(f"Project '{pid}' not found.")
        return
    history_dir = Path.home() / ".nexus_audit" / "projects" / pid / "jobs"
    job_count   = sum(1 for _ in history_dir.iterdir()) if history_dir.exists() else 0
    ctx.write(f"Name       : {proj.name}")
    ctx.write(f"ID         : {pid}")
    ctx.write(f"Path       : {proj.path}")
    ctx.write(f"Scanners   : {len(proj.settings.scanners)}")
    ctx.write(f"Audit runs : {job_count}")


async def _handle_delete(ctx, params):
    pid = params["project_id"]
    if pid not in ctx.workspace.projects:
        ctx.write_error(f"Project '{pid}' not found.")
        return
    await ctx.settings_manager.delete_project(pid)
    ctx.mark_dirty()
    ctx.write(f"Project '{pid}' deleted.")


async def _handle_clear(ctx, params):
    if not params.get("force"):
        ctx.write_error("Pass --force to confirm deletion of all projects.")
        return
    ids = list(ctx.workspace.projects.keys())
    for pid in ids:
        await ctx.settings_manager.delete_project(pid)
    ctx.mark_dirty()
    ctx.write(f"Cleared {len(ids)} project(s).")
