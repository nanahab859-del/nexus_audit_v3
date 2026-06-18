import asyncio
from core.primitives.commands.context import READONLY
from core.primitives.events import EventType


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="log:stream",
        description="Stream live log events from the audit engine.",
        usage="log:stream [--follow]",
        handler=_handle_stream,
        required_privilege=READONLY,
        parser=CommandParser("log:stream").add_argument("--follow", action="store_true"),
    ))


async def _handle_stream(ctx, params):
    orch = getattr(ctx, "orchestrator", None)
    if not orch:
        ctx.write_error("Orchestrator not available.")
        return
    if not params.get("follow"):
        ctx.write("Use 'log:stream --follow' to subscribe to live events.")
        return
    # This works correctly only inside the persistent event loop in cli.py.
    q     = asyncio.Queue()
    token = await orch.bus.subscribe(EventType.LOG, lambda e: q.put_nowait(e))
    ctx.write("Subscribed to log stream. Press Ctrl+C to stop.\n")
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=30.0)
            ctx.write(f"[{event.timestamp:%H:%M:%S}] {event.payload.get('message', '')}")
    except asyncio.TimeoutError:
        ctx.write("Stream idle for 30s — unsubscribing.")
    except asyncio.CancelledError:
        pass
    finally:
        await orch.bus.unsubscribe(token)
