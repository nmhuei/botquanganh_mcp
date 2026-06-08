# tests/test_approval_no_sse.py
import asyncio
import pytest
from app import event_bus

@pytest.mark.anyio
async def test_resolve_approval_threadsafe():
    """resolve_approval từ thread khác không raise RuntimeError"""
    import threading
    fut = event_bus.register_approval("goal_test")

    def approve_from_thread():
        import time
        time.sleep(0.05)
        event_bus.resolve_approval("goal_test", True)

    threading.Thread(target=approve_from_thread).start()
    result = await asyncio.wait_for(fut, timeout=2.0)
    assert result is True

@pytest.mark.anyio
async def test_approval_without_sse_subscriber():
    """agent_approve hoạt động dù không có SSE subscriber"""
    fut = event_bus.register_approval("goal_no_sse")
    assert event_bus.pending_approval("goal_no_sse")

    # Simulate agent_approve (sync, từ thread pool)
    import threading
    def do_approve():
        event_bus.resolve_approval("goal_no_sse", True)
    threading.Thread(target=do_approve).start()

    result = await asyncio.wait_for(fut, timeout=2.0)
    assert result is True
    assert not event_bus.pending_approval("goal_no_sse")
