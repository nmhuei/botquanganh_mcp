import asyncio
import json
import pytest
from starlette.datastructures import QueryParams
from app.sse_events import sse_events_endpoint
from app import event_bus

class MockRequest:
    def __init__(self, goal_id: str, token: str = ""):
        self.path_params = {"goal_id": goal_id}
        self.query_params = QueryParams(f"token={token}")

@pytest.mark.anyio
async def test_sse_endpoint_auth(monkeypatch):
    monkeypatch.setattr("app.sse_events.GATEWAY_TOKEN", "my-secure-token")
    monkeypatch.setattr("app.auth.GATEWAY_TOKEN", "my-secure-token")
    
    # 1. Unauthorized
    req = MockRequest("goal1", "wrong-token")
    res = await sse_events_endpoint(req)
    assert res.status_code == 401
    
    # 2. Authorized
    req = MockRequest("goal1", "my-secure-token")
    res = await sse_events_endpoint(req)
    assert res.status_code == 200

@pytest.mark.anyio
async def test_sse_endpoint_stream(monkeypatch):
    monkeypatch.setattr("app.sse_events.GATEWAY_TOKEN", "")
    monkeypatch.setattr("app.auth.GATEWAY_TOKEN", "")
    
    req = MockRequest("goal2")
    res = await sse_events_endpoint(req)
    assert res.status_code == 200
    
    # Let's read some items from the body generator
    generator = res.body_iterator
    
    # First chunk is the "connected" event
    first_chunk = await generator.__anext__()
    first_str = first_chunk if isinstance(first_chunk, str) else first_chunk.decode()
    assert "connected" in first_str
    
    # Publish an event to the queue
    event_bus.publish("goal2", {"type": "step", "index": 1})
    
    second_chunk = await generator.__anext__()
    second_str = second_chunk if isinstance(second_chunk, str) else second_chunk.decode()
    assert "step" in second_str
    assert '"index": 1' in second_str
