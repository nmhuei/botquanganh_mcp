import asyncio
from typing import Dict, Set

# Dict mapping goal_id to a set of asyncio.Queue
_listeners: Dict[str, Set[asyncio.Queue]] = {}

def subscribe(goal_id: str) -> asyncio.Queue:
    queue = asyncio.Queue()
    if goal_id not in _listeners:
        _listeners[goal_id] = set()
    _listeners[goal_id].add(queue)
    return queue

def unsubscribe(goal_id: str, queue: asyncio.Queue):
    if goal_id in _listeners:
        _listeners[goal_id].discard(queue)
        if not _listeners[goal_id]:
            del _listeners[goal_id]

def publish(goal_id: str, event: dict):
    if goal_id in _listeners:
        for queue in _listeners[goal_id]:
            queue.put_nowait(event)

def has_subscribers(goal_id: str) -> bool:
    return goal_id in _listeners and bool(_listeners[goal_id])

# Approval registry for active WebSocket approval sessions
# Dict mapping goal_id to an asyncio.Future that resolves when approved
_approvals: Dict[str, asyncio.Future] = {}

def register_approval(goal_id: str) -> "asyncio.Future[bool]":
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    _approvals[goal_id] = fut
    return fut

def resolve_approval(goal_id: str, approved: bool) -> None:
    fut = _approvals.pop(goal_id, None)
    if fut and not fut.done():
        try:
            fut.get_loop().call_soon_threadsafe(fut.set_result, approved)
        except RuntimeError:
            # Loop đã đóng (server shutdown), bỏ qua
            pass

def pending_approval(goal_id: str) -> bool:
    return goal_id in _approvals
