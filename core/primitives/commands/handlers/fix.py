from pathlib import Path
from core.primitives.commands.context import READONLY, OPERATOR


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="fix:list",
        description="List findings in the fix queue.",
        usage="fix:list [--status STATUS] [--limit N]",
        handler=_handle_list,
        required_privilege=READONLY,
        parser=(
            CommandParser("fix:list")
            .add_argument("--status", default=None,
                          help="Filter by status: open | in_progress | done | snoozed")
            .add_argument("--limit", type=int, default=20)
        ),
    ))

    registry.register(Command(
        name="fix:show",
        description="Show full detail for one finding.",
        usage="fix:show <finding_id>",
        handler=_handle_show,
        required_privilege=READONLY,
        parser=CommandParser("fix:show").add_argument("finding_id"),
    ))

    registry.register(Command(
        name="fix:mark",
        description="Update the status of a finding.",
        usage="fix:mark <finding_id> <status>",
        handler=_handle_mark,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("fix:mark")
            .add_argument("finding_id")
            .add_argument("status", choices=["open", "in_progress", "done", "snoozed"])
        ),
    ))

    registry.register(Command(
        name="fix:note",
        description="Append a note to a finding.",
        usage="fix:note <finding_id> <text>",
        handler=_handle_note,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("fix:note")
            .add_argument("finding_id")
            .add_argument("text")
        ),
    ))


def _queue_for(ctx):
    from core.engines.fix_queue import FixQueue
    path = Path(ctx.active_project.settings.project_path) / ".nexus_fix_queue.json"
    return FixQueue(path)


async def _handle_list(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    fq     = _queue_for(ctx)
    await fq.load()                     # public method
    status = params.get("status")
    limit  = params.get("limit", 20)
    count  = 0
    for entry in fq.entries():          # public method
        if status and entry.get("status") != status:
            continue
        fp  = entry.get("fingerprint", "")[:12]
        st  = entry.get("status", "?")
        msg = entry.get("message", "")[:60]
        ctx.write(f"  {fp}  [{st:<12}]  {msg}")
        count += 1
        if count >= limit:
            break
    if count == 0:
        ctx.write("No findings match the filter.")


async def _handle_show(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    fq    = _queue_for(ctx)
    await fq.load()
    entry = fq.get_entry(params["finding_id"])   # public method with prefix matching
    if entry:
        ctx.write_json(entry)
    else:
        ctx.write_error(f"Finding '{params['finding_id']}' not found.")


async def _handle_mark(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    fq = _queue_for(ctx)
    await fq.update_status(params["finding_id"], params["status"])
    ctx.write(f"Marked '{params['finding_id'][:12]}' as {params['status']}.")


async def _handle_note(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    fq    = _queue_for(ctx)
    await fq.load()
    entry = fq.get_entry(params["finding_id"])
    if not entry:
        ctx.write_error(f"Finding '{params['finding_id']}' not found.")
        return
    await fq.update_status(
        params["finding_id"],
        entry.get("status", "open"),
        note=params["text"]
    )
    ctx.write("Note added.")
