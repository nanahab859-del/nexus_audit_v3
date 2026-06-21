import asyncio
from core.primitives.commands.context import READONLY
from core.primitives.events import EventType


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="log:stream",
        description="Stream live log events from the audit engine.",
        usage="log:stream [--follow] [--all]",
        handler=_handle_stream,
        required_privilege=READONLY,
        parser=(
            CommandParser("log:stream")
            .add_argument("--follow", action="store_true",
                          help="Stay connected and print events as they arrive")
            .add_argument("--all", action="store_true",
                          help="Show all event types, not just LOG")
        ),
    ))


async def _handle_stream(ctx, params) -> None:
    orch = getattr(ctx, "orchestrator", None)
    if not orch:
        ctx.write_error("Orchestrator not available.")
        return

    if not params.get("follow"):
        # Print recent history and exit
        history = orch.bus.get_history()
        if not history:
            ctx.write("No events in history. Start an audit with 'audit:run'.")
            ctx.write("Use 'log:stream --follow' to subscribe to live events.")
            return
        for _, event in history[-50:]:
            _print_event(ctx, event, live=False)
        return

    # --follow mode: subscribe and stream live events
    # Uses write_live() so events appear immediately — ctx.write() would
    # buffer silently until the handler returns (which it never does).
    q     = asyncio.Queue()
    show_all = params.get("all", False)
    event_type = None if show_all else EventType.LOG

    if event_type is None:
        token = await orch.bus.subscribe_all(lambda eid, e: q.put_nowait(e))
    else:
        token = await orch.bus.subscribe(event_type, lambda e: q.put_nowait(e))

    ctx.write_live("Subscribed to log stream. Press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                _print_event(ctx, event, live=True)
                q.task_done()
            except asyncio.TimeoutError:
                # Check if job is still running
                status = orch.status()
                state  = status.get("state", "idle")
                if state not in ("running", "pending"):
                    ctx.write_live(f"\nJob {state}. Unsubscribing.")
                    break
                # Still running — keep waiting
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        await orch.bus.unsubscribe(token)
        ctx.write_live("")


def _print_event(ctx, event, live: bool) -> None:
    """Format and write a single event."""
    ts      = event.timestamp.strftime("%H:%M:%S")
    payload = event.payload

    if event.type.value == "status" and payload.get("state") == "phase":
        # Phase boundary — render as a distinct progress line
        idx   = payload.get("phase_index", "?")
        total = payload.get("phase_total", "?")
        phase = payload.get("phase", "?")
        line  = f"[{ts}] ── Phase {idx}/{total}: {phase}"

    elif event.type.value == "status":
        state  = payload.get("state", "?")
        job_id = (payload.get("job_id") or "")[:8]
        line   = f"[{ts}] [STATUS] {state} {job_id}"

    elif event.type.value == "log":
        level = payload.get("level", "INFO").upper()
        msg   = payload.get("message", "")
        line  = f"[{ts}] [{level}] {msg}"

    elif event.type.value == "progress":
        scanner = payload.get("scanner", "?")
        pct     = payload.get("percent", 0)
        file_   = payload.get("file", "")
        line    = f"[{ts}] [{scanner}] {pct:>3}% {file_}"

    else:
        typ  = event.type.value.upper()
        line = f"[{ts}] [{typ}] {payload}"

    if live:
        ctx.write_live(line)
    else:
        ctx.write(line)
