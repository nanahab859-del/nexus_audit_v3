"""SSE stream endpoint — Server-Sent Events for real-time updates."""

import asyncio
import json
import sys

from aiohttp import web

from core.events import Event, EventType, bus


async def get_stream(request: web.Request) -> web.StreamResponse:
    """GET /api/stream — SSE endpoint with event replay."""
    # Always replay full history on connect (Last-Event-ID is unreliable)
    since_index = 0

    # Set up SSE response headers
    response = web.StreamResponse()
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    await response.prepare(request)

    # Create a queue for this connection's events
    queue: asyncio.Queue[Event | None] = asyncio.Queue()

    async def enqueue_event(event: Event) -> None:
        """Callback to enqueue events."""
        await queue.put(event)

    # Subscribe to all event types
    tokens = [bus.subscribe(et, enqueue_event) for et in EventType]

    event_id = 0

    try:
        # Replay full buffered history
        for event in bus.history(0):
            await _send_sse_event(response, event, event_id)
            event_id += 1

        # Send heartbeat and new events
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                if event is None:
                    break

                await _send_sse_event(response, event, event_id)
                event_id += 1

            except asyncio.TimeoutError:
                # Send heartbeat to prevent timeout
                await response.write(b": heartbeat\n\n")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"SSE error: {e}", file=sys.stderr)
    finally:
        # Clean up subscriptions
        for token in tokens:
            bus.unsubscribe(token)

        await response.write_eof()

    return response


async def _send_sse_event(
    response: web.StreamResponse, event: Event, event_id: int
) -> None:
    """Send a single SSE event."""
    sse_lines = [
        f"id: {event_id}".encode(),
        f"event: {event.type.value}".encode(),
        f"data: {json.dumps(event.payload)}".encode(),
        b"",
    ]

    await response.write(b"\n".join(sse_lines) + b"\n\n")
