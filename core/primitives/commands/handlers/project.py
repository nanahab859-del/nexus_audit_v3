from pathlib import Path
from core.primitives.commands.context import READONLY, ADMIN
from core.primitives.commands.handlers._utils import resolve_project_id


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
        description="Show details for a project. Accepts full UUID or 8-char prefix.",
        usage="project:info [project_id]",
        handler=_handle_info,
        required_privilege=READONLY,
        parser=CommandParser("project:info").add_argument("project_id", nargs="?", default=None),
    ))

    registry.register(Command(
        name="project:delete",
        description="Delete a registered project. Accepts full UUID or 8-char prefix.",
        usage="project:delete <project_id> [project_id ...]",
        handler=_handle_delete,
        required_privilege=ADMIN,
        parser=CommandParser("project:delete").add_argument(
            "project_id", nargs="+",
            help="One or more project IDs or 8-char prefixes"
        ),
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
    proj = await ctx.settings_manager.register_project(name, path)
    ctx.mark_dirty()
    ctx.write(f"Project '{name}' registered at {path}")
    ctx.write(f"  ID prefix : {proj.id[:8]}")
    ctx.write(f"  Activate  : workspace:active {proj.id[:8]}")


async def _handle_list(ctx, params):
    if not ctx.workspace.projects:
        ctx.write("No projects registered.")
        return
    active_id = ctx.workspace.active_project_id
    ctx.write(f"  {'ID':<10} {'NAME':<24} PATH")
    ctx.write(f"  {'─'*10} {'─'*24} {'─'*40}")
    for pid, proj in sorted(
        ctx.workspace.projects.items(),
        key=lambda kv: getattr(kv[1], "registered_at", ""),
        reverse=True
    ):
        marker = " *" if pid == active_id else "  "
        ctx.write(f"{marker} {pid[:8]}  {proj.name:<24}  {proj.path}")
    ctx.write("")
    ctx.write("Use 'workspace:active <ID>' with the 8-char prefix shown above.")


async def _handle_info(ctx, params):
    raw = params.get("project_id")

    if raw:
        # Resolve the prefix to a full UUID
        full_pid = resolve_project_id(ctx, raw)
        if full_pid is None:
            return   # error already written
    elif ctx.active_project:
        full_pid = ctx.active_project.id
    else:
        ctx.write_error("Provide a project_id or set an active project.")
        return

    try:
        proj = await ctx.settings_manager.load_project(full_pid)
    except FileNotFoundError:
        ctx.write_error(f"Project '{full_pid[:8]}' not found.")
        return

    history_dir = Path.home() / ".nexus_audit" / "projects" / full_pid / "jobs"
    job_count   = sum(1 for _ in history_dir.iterdir()) if history_dir.exists() else 0

    ctx.write(f"Name       : {proj.name}")
    ctx.write(f"ID         : {full_pid}")
    ctx.write(f"Path       : {proj.path}")
    ctx.write(f"Scanners   : {len(proj.settings.scanners)}")
    ctx.write(f"Audit runs : {job_count}")


async def _handle_delete(ctx, params):
    project_ids = params["project_id"]
    if isinstance(project_ids, str):
        project_ids = [project_ids]

    deleted = []
    for raw_id in project_ids:
        full_pid = resolve_project_id(ctx, raw_id)
        if full_pid is None:
            continue
        name = ctx.workspace.projects[full_pid].name
        await ctx.settings_manager.delete_project(full_pid)
        ctx.mark_dirty()
        deleted.append(f"'{name}' ({full_pid[:8]})")

    if deleted:
        ctx.write(f"Deleted: {', '.join(deleted)}")


async def _handle_clear(ctx, params):
    if not params.get("force"):
        ctx.write_error("Pass --force to confirm deletion of all projects.")
        return
    ids = list(ctx.workspace.projects.keys())
    for pid in ids:
        await ctx.settings_manager.delete_project(pid)
    ctx.mark_dirty()
    ctx.write(f"Cleared {len(ids)} project(s).")
