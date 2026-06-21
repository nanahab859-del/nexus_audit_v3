import asyncio
import json
import time
from pathlib import Path
from core.primitives.commands.context import READONLY, OPERATOR
from core.primitives.events import EventType
import logging

logger = logging.getLogger(__name__)


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="audit:run",
        description="Start an audit job on the active project.",
        usage="audit:run [--scanner NAME] [--fast] [--force] [--follow]",
        handler=_handle_run,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("audit:run")
            .add_argument("--scanner", default=None, help="Limit to one scanner by name")
            .add_argument("--fast",    action="store_true", help="Only scan changed files (git diff)")
            .add_argument("--force",   action="store_true", help="Bypass dependency cache")
            .add_argument("--follow",  action="store_true", help="Stream logs until job completes")
        ),
    ))

    registry.register(Command(
        name="audit:cancel",
        description="Cancel the currently running audit job and wait for it to stop.",
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
        description="List recent audit runs. Add --all to include failed/empty jobs.",
        usage="audit:history [--limit N] [--all]",
        handler=_handle_history,
        required_privilege=READONLY,
        parser=(
            CommandParser("audit:history")
            .add_argument("--limit", type=int, default=10)
            .add_argument("--all",   action="store_true",
                          help="Show all jobs including failed ones")
        ),
    ))


async def _handle_run(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return
    orch = _require_orchestrator(ctx)
    if orch is None:
        return

    await ctx.settings_manager.load_project(ctx.active_project.id)
    fast   = params.get("fast", False)
    follow = params.get("follow", False)

    if follow:
        q            = asyncio.Queue()
        log_token    = await orch.bus.subscribe(EventType.LOG,      lambda e: q.put_nowait(e))
        status_token = await orch.bus.subscribe(EventType.STATUS,   lambda e: q.put_nowait(e))
        prog_token   = await orch.bus.subscribe(EventType.PROGRESS, lambda e: q.put_nowait(e))

        try:
            job = await orch.start_job(ctx.active_project.id, fast_mode=fast)
        except RuntimeError as e:
            ctx.write_error(str(e))
            await orch.bus.unsubscribe(log_token)
            await orch.bus.unsubscribe(status_token)
            await orch.bus.unsubscribe(prog_token)
            return

        ctx.write_live(f"Audit started: {job.id}")
        ctx.write_live(f"Fast mode    : {'yes' if fast else 'no'}")
        ctx.write_live("Streaming logs — press Ctrl+C to detach (job continues).\n")

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=120.0)
                    _live_event(ctx, event)
                    q.task_done()
                    if event.type == EventType.STATUS:
                        state = event.payload.get("state", "")
                        if state in ("completed", "failed", "cancelled"):
                            ctx.write_live(f"\nJob {state}.")
                            break
                except asyncio.TimeoutError:
                    ctx.write_live("Stream idle 120s — detaching (job still runs).")
                    break
        except (asyncio.CancelledError, KeyboardInterrupt):
            ctx.write_live("\n[INTERRUPT] Detached. Job continues in background.")
        finally:
            await orch.bus.unsubscribe(log_token)
            await orch.bus.unsubscribe(status_token)
            await orch.bus.unsubscribe(prog_token)
            # Live output was already printed directly via click.echo inside write_live().
            # Clear the buffer so the CLI's _render() does not print everything a second time.
            ctx.stdout_buffer.clear()
    else:
        try:
            job = await orch.start_job(ctx.active_project.id, fast_mode=fast)
        except RuntimeError as e:
            ctx.write_error(str(e))
            return
        ctx.write(f"Audit started  : job {job.id}")
        ctx.write(f"Fast mode      : {'yes' if fast else 'no'}")
        ctx.write("Poll with 'audit:status' or stream with 'log:stream --follow'.")


async def _handle_cancel(ctx, params):
    orch = _require_orchestrator(ctx)
    if orch is None:
        return

    status = orch.status()
    if status.get("state") not in ("running", "pending"):
        ctx.write_error("No audit is currently running.")
        return

    await orch.cancel_job()
    ctx.write("Cancellation requested — waiting for job to stop...")

    for _ in range(20):
        await asyncio.sleep(0.5)
        current = orch.status().get("state", "idle")
        if current not in ("running", "pending"):
            ctx.write(f"Job stopped. Final state: {current}")
            return

    ctx.write("Job did not stop within 10s — may still be finishing a scanner subprocess.")
    ctx.write(f"Current state: {orch.status().get('state', '?')}")


async def _handle_status(ctx, params):
    orch = _require_orchestrator(ctx)
    if orch is None:
        return
    status = orch.status()
    ctx.write(f"State  : {status.get('state', 'idle')}")
    ctx.write(f"Job ID : {status.get('job_id') or '—'}")


async def _handle_history(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return

    limit    = params.get("limit", 10)
    show_all = params.get("all", False)
    history_dir = (
        Path.home() / ".nexus_audit" / "projects" / ctx.active_project.id / "jobs"
    )
    if not history_dir.exists():
        ctx.write("No audit history found.")
        return

    # Sort by filesystem mtime so newest jobs always appear first,
    # regardless of UUID string order (UUIDs are random — alphabetical sort
    # does NOT equal chronological order).
    jobs = sorted(history_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    if not jobs:
        ctx.write("No audit history found.")
        return

    now   = time.time()
    shown = 0

    for job_dir in jobs:
        summary_f  = job_dir / "audit_summary.json"
        complete_f = job_dir / "audit_data_complete.json"
        log_f      = job_dir / "audit.log"
        age_mins   = (now - job_dir.stat().st_mtime) / 60

        if summary_f.exists():
            try:
                s        = json.loads(summary_f.read_text())
                score    = s.get("fleet_average", "?")
                findings = s.get("findings_count", "?")
                ctx.write(f"  {job_dir.name[:8]}  score={score:<5} findings={findings}")
                shown += 1
            except Exception as e:
                logger.warning("Cannot read audit summary %s: %s", job_dir.name[:8], e)
                ctx.write(f"  {job_dir.name[:8]}  (summary unreadable)")
                shown += 1

        elif complete_f.exists():
            ctx.write(f"  {job_dir.name[:8]}  completed (no summary)")
            shown += 1

        elif log_f.exists():
            if age_mins < 5:
                ctx.write(f"  {job_dir.name[:8]}  running...")
            else:
                ctx.write(f"  {job_dir.name[:8]}  failed — partial run")
            shown += 1

        else:
            # No useful data — only show with --all
            if show_all:
                if age_mins < 5:
                    ctx.write(f"  {job_dir.name[:8]}  running...")
                else:
                    ctx.write(f"  {job_dir.name[:8]}  no data")
                shown += 1

    if shown == 0:
        ctx.write("No completed audit runs found.")
        ctx.write("Run 'audit:run' to start an audit.")
    elif not show_all:
        ctx.write("")
        ctx.write("Tip: use 'audit:history --all' to include jobs with no data.")


def _require_orchestrator(ctx):
    orch = getattr(ctx, "orchestrator", None)
    if orch is None:
        ctx.write_error("Orchestrator not available — server is in read-only mode.")
    return orch


def _live_event(ctx, event) -> None:
    ts      = event.timestamp.strftime("%H:%M:%S")
    payload = event.payload

    if event.type == EventType.STATUS and payload.get("state") == "phase":
        idx   = payload.get("phase_index", "?")
        total = payload.get("phase_total", "?")
        phase = payload.get("phase", "?")
        ctx.write_live(f"[{ts}] ── Phase {idx}/{total}: {phase}")
    elif event.type == EventType.STATUS:
        state  = payload.get("state", "?")
        job_id = (payload.get("job_id") or "")[:8]
        ctx.write_live(f"[{ts}] [STATUS] {state} {job_id}")
    elif event.type == EventType.LOG:
        level = payload.get("level", "INFO").upper()
        msg   = payload.get("message", "")
        ctx.write_live(f"[{ts}] [{level}] {msg}")
    elif event.type == EventType.PROGRESS:
        scanner = payload.get("scanner", "?")
        pct     = payload.get("percent", 0)
        file_   = payload.get("file", "")
        ctx.write_live(f"[{ts}] [{scanner}] {pct:>3}% {file_}")
    else:
        ctx.write_live(f"[{ts}] [{event.type.value.upper()}] {payload}")
