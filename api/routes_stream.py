import asyncio
import json
from aiohttp import web
from core.primitives.events import Event, EventType


async def stream(request: web.Request) -> web.Response:
    bus = request.app['bus']

    response = web.StreamResponse(
        status=200, reason='OK',
        headers={
            'Content-Type':  'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection':    'keep-alive',
        },
    )
    await response.prepare(request)

    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event_id: int, event: Event) -> None:
        await queue.put((event_id, event))

    # subscribe_all is async — must be awaited. Returns a token for unsubscription.
    token = await bus.subscribe_all(on_event)

    try:
        last_id_str = request.headers.get("Last-Event-ID", "0")
        try:
            last_id = int(last_id_str)
        except ValueError:
            last_id = 0

        for eid, event in bus.get_history(last_id):
            # Fix 10: use event.payload, not event.data
            payload = (
                f"id: {eid}\n"
                f"event: {event.type.value}\n"
                f"data: {json.dumps(event.payload)}\n\n"
            )
            await response.write(payload.encode('utf-8'))

        while True:
            eid, event = await queue.get()
            payload = (
                f"id: {eid}\n"
                f"event: {event.type.value}\n"
                f"data: {json.dumps(event.payload)}\n\n"
            )
            await response.write(payload.encode('utf-8'))
            queue.task_done()

    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        # unsubscribe is also async — must be awaited to actually remove the subscriber.
        await bus.unsubscribe(token)

    return response
