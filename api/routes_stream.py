import asyncio
import json
from aiohttp import web
from core.events import Event, EventType

async def stream(request: web.Request) -> web.Response:
    bus = request.app['bus']
    
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)
    
    queue = asyncio.Queue()
    
    async def on_event(event_id: int, event: Event):
        await queue.put((event_id, event))
        
    bus.subscribe_all(on_event)
    
    try:
        # Replay history
        last_id_str = request.headers.get("Last-Event-ID", "0")
        try:
            last_id = int(last_id_str)
        except ValueError:
            last_id = 0
            
        history = bus.get_history(last_id)
        for eid, event in history:
            payload = f"id: {eid}\nevent: {event.type.value}\ndata: {json.dumps(event.data)}\n\n"
            await response.write(payload.encode('utf-8'))
            
        # Stream new events
        while True:
            eid, event = await queue.get()
            payload = f"id: {eid}\nevent: {event.type.value}\ndata: {json.dumps(event.data)}\n\n"
            await response.write(payload.encode('utf-8'))
            queue.task_done()
    except (asyncio.CancelledError, ConnectionResetError):
        # Client disconnected
        pass
    finally:
        bus.unsubscribe_all(on_event)
            
    return response
