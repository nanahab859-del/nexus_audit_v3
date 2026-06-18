from pathlib import Path
from core.primitives.commands.context import READONLY, OPERATOR


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="audit:run",
        description="Start an audit job on the active project.",
        usage="audit:run [--scanner NAME] [--fast] [--force]",
        handler=_handle_run,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("audit:run")
            .add_argument("--scanner", default=None, help="Limit to one scanner by name")
            .add_argument("--fast",    action="store_true", help="Only scan changed files (git diff)")
            .add_argument("--force",   action="store_true", help="Bypass dependency cache")
        ),
    ))

    registry.register(Command(
        name="audit:cancel",
        description="Cancel the currently running audit job.",
        usage="audit:cancel",
        handler=_handle_cancel,
        required_privilege=OPERATOR,
    ))

    registry.register(Command(
        name="audit:status",
        description="Show the state of the current or last audit job.",
        usage="audit:status",
        handler=_handle_status,
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="audit:history",
        description="List recent audit runs for the active project.",
        usage="audit:history [--limit N]",
        handler=_handle_history,
        required_privilege=READONLY,
        parser=CommandParser("audit:history").add_argument("--limit", type=int, default=10),
    ))


async def _handle_run(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return
    orch = _require_orchestrator(ctx)
    if orch is None:
        return
    # Ensure project is in the settings manager cache before starting the job
    await ctx.settings_manager.load_project(ctx.active_project.id)
    fast = params.get("fast", False)
    job  = await orch.start_job(ctx.active_project.id, fast_mode=fast)
    ctx.write(f"Audit started  : job {job.id}")
    ctx.write(f"Fast mode      : {'yes' if fast else 'no'}")
    ctx.write("Poll with 'audit:status' or watch with 'log:stream --follow'.")


async def _handle_cancel(ctx, params):
    orch = _require_orchestrator(ctx)
    if orch is None:
        return
    await orch.cancel_job()
    ctx.write("Cancel signal sent.")


async def _handle_status(ctx, params):
    orch = _require_orchestrator(ctx)
    if orch is None:
        return
    status = orch.status()   # synchronous — returns a plain dict immediately
    ctx.write(f"State  : {status.get('state',  'idle')}")
    ctx.write(f"Job ID : {status.get('job_id') or '—'}")


async def _handle_history(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    import json
    limit       = params.get("limit", 10)
    history_dir = Path.home() / ".nexus_audit" / "projects" / ctx.active_project.id / "jobs"
    if not history_dir.exists():
        ctx.write("No audit history found.")
        return
    jobs = sorted(history_dir.iterdir(), reverse=True)[:limit]
    if not jobs:
        ctx.write("No audit history found.")
        return
    for job_dir in jobs:
        sf = job_dir / "audit_summary.json"
        if sf.exists():
            try:
                s = json.loads(sf.read_text())
                ctx.write(
                    f"  {job_dir.name[:8]}  "
                    f"score={s.get('fleet_average','?')}  "
                    f"findings={s.get('findings_count','?')}"
                )
            except Exception:
                ctx.write(f"  {job_dir.name[:8]}  (summary unreadable)")
        else:
            ctx.write(f"  {job_dir.name[:8]}  (no summary)")


def _require_orchestrator(ctx):
    """Return ctx.orchestrator or write an error and return None."""
    orch = getattr(ctx, "orchestrator", None)
    if orch is None:
        ctx.write_error("Orchestrator not available — server is in read-only mode.")
    return orch
