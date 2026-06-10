# app/sse_events.py
import asyncio
import hmac
import json
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route
from app import event_bus
from app.config import GATEWAY_TOKEN

HEARTBEAT_INTERVAL = 15  # seconds

async def sse_events_endpoint(request: Request) -> Response:
    goal_id = request.path_params["goal_id"]

    # Auth: SSE client không thể set Authorization header qua EventSource
    # → chấp nhận token qua query param CHỈ cho endpoint này
    token = request.query_params.get("token", "")
    if GATEWAY_TOKEN and not hmac.compare_digest(str(token), str(GATEWAY_TOKEN)):
        return Response("Unauthorized", status_code=401)

    async def event_stream():
        queue = event_bus.subscribe(goal_id)
        try:
            yield f"data: {json.dumps({'type': 'connected', 'goal_id': goal_id})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # SSE comment, giữ connection alive
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(goal_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # tắt nginx buffering nếu có proxy
            "Connection": "keep-alive",
        },
    )

# Route object để mount vào app
sse_route = Route("/events/{goal_id}", endpoint=sse_events_endpoint, methods=["GET"])
