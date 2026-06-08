
Đủ context rồi. Để plan chính xác hơn, tôi đọc lại code hiện tại trước:Đủ thông tin rồi. Viết plan:

---

# Phase 3 — SSE Event Stream + Approval Tool

## Bức tranh tổng thể

Trước khi implement, cần hiểu rõ constraint quan trọng: **ChatGPT web không thể tự mở SSE connection** từ phía tool call. ChatGPT chỉ có thể gọi MCP tools (HTTP request → response). Vì vậy kiến trúc phải là:

* **SSE endpoint** (`GET /events/{goal_id}`) — dành cho một browser tab riêng hoặc script monitoring, không phải GPT trực tiếp subscribe.
* **GPT side** dùng polling qua `agent_status` tool, hoặc GPT hướng dẫn user mở URL SSE trong browser để xem live stream.
* **Approval** — GPT gọi `agent_approve(goal_id)` sau khi user confirm trong chat → MCP tool resolve Future → `agent_goal_start` loop tiếp tục.

Hiện tại `event_bus.publish` đã được gọi trong `_append_event`, và `event_bus.register_approval` / `resolve_approval` đã có. Việc còn lại: (1) mount SSE HTTP endpoint, (2) thêm `agent_approve` MCP tool, (3) bỏ WebSocket khỏi `event_bus`, (4) fix `get_event_loop`.

---

## Bước 0 — Fix 3 lỗi trước (prerequisite)

### 0.1 Token trong query string

`app/mcp_server.py` — trong `TokenAuthMiddleware.__call__`, xóa block:

```python
# XÓA đoạn này:
if not token:
    for q_key in ("token", "gateway_token", "authorization"):
        if q_key in params:
            token = params[q_key][0]
            break
```

Chỉ giữ `Authorization: Bearer` header và `X-Gateway-Token` header. SSE client dùng `EventSource` API không set custom header được — nhưng ChatGPT web gọi qua MCP tool (HTTP), không phải EventSource trực tiếp, nên không ảnh hưởng.

**Lưu ý quan trọng:** nếu sau này muốn browser EventSource subscribe SSE endpoint mà cần auth, dùng query param `?token=` chỉ cho path `/events/*` thôi, không phải toàn bộ middleware. Sẽ cover ở Bước 2.

### 0.2 `get_event_loop` deprecated

`app/event_bus.py` — `register_approval`:

```python
# CŨ:
loop = asyncio.get_event_loop()
fut = loop.create_future()

# MỚI:
loop = asyncio.get_running_loop()
fut = loop.create_future()
```

`get_running_loop()` raise `RuntimeError` nếu không có loop đang chạy — đây là behavior đúng, vì `register_approval` chỉ được gọi từ trong `async def agent_step`.

### 0.3 Untrack logs đã bị commit

```bash
git rm -r --cached logs/
echo "logs/" >> .gitignore   # đã có nhưng đảm bảo
git commit -m "chore: untrack committed log files"
```

---

## Bước 1 — Refactor `event_bus.py`

Bỏ hết phần WebSocket, chỉ giữ pub/sub queue và approval Future. File mới gọn lại:

```python
# app/event_bus.py
import asyncio
import json
from typing import Dict, Set

# --- Pub/Sub cho SSE streaming ---
_listeners: Dict[str, Set[asyncio.Queue]] = {}

def subscribe(goal_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _listeners.setdefault(goal_id, set()).add(q)
    return q

def unsubscribe(goal_id: str, queue: asyncio.Queue) -> None:
    if goal_id in _listeners:
        _listeners[goal_id].discard(queue)
        if not _listeners[goal_id]:
            del _listeners[goal_id]

def publish(goal_id: str, event: dict) -> None:
    for q in _listeners.get(goal_id, set()):
        q.put_nowait(event)

def has_subscribers(goal_id: str) -> bool:
    return bool(_listeners.get(goal_id))

# --- Approval gate ---
_approvals: Dict[str, asyncio.Future] = {}

def register_approval(goal_id: str) -> "asyncio.Future[bool]":
    loop = asyncio.get_running_loop()   # FIX: không dùng get_event_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    _approvals[goal_id] = fut
    return fut

def resolve_approval(goal_id: str, approved: bool) -> None:
    fut = _approvals.pop(goal_id, None)
    if fut and not fut.done():
        fut.set_result(approved)

def pending_approval(goal_id: str) -> bool:
    return goal_id in _approvals
```

Không có gì khác — không import `websockets`, không WebSocket handler.

---

## Bước 2 — SSE endpoint (`app/sse_events.py`)

Tạo file mới. Đây là Starlette endpoint thuần, không liên quan FastMCP:

```python
# app/sse_events.py
import asyncio
import json
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from app import event_bus
from app.auth import verify_token
from app.config import GATEWAY_TOKEN

HEARTBEAT_INTERVAL = 15  # seconds

async def sse_events_endpoint(request: Request) -> Response:
    goal_id = request.path_params["goal_id"]

    # Auth: SSE client không thể set Authorization header qua EventSource
    # → chấp nhận token qua query param CHỈ cho endpoint này
    token = request.query_params.get("token", "")
    if GATEWAY_TOKEN and not verify_token(token):
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

    return Response(
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
```

**Tại sao query param auth chỉ cho endpoint này:** EventSource browser API không cho phép set custom header. Nếu dùng `fetch` với `ReadableStream` thì set header được, nhưng EventSource đơn giản hơn. Scope token-in-URL ở đây là chấp nhận được vì: (1) endpoint chỉ đọc, không write, (2) scoped path cụ thể `/events/*`, không phải toàn bộ MCP API.

---

## Bước 3 — Mount SSE route vào FastMCP app

Sửa `patched_http_app` trong `app/mcp_server.py`:

```python
from app.sse_events import sse_route

def patched_http_app(self, *args, **kwargs):
    app = original_http_app(self, *args, **kwargs)
    transport = kwargs.get("transport", "http")

    # Inject SSE events route
    app.router.routes.append(sse_route)

    app.add_middleware(TokenAuthMiddleware)

    if transport == "sse":
        # ... existing SSE route combining logic ...
        pass

    return app
```

**Thứ tự quan trọng:** append `sse_route` trước khi `add_middleware` để middleware bọc toàn bộ kể cả SSE endpoint. `TokenAuthMiddleware` sẽ pass-through `/events/*` vì `sse_events_endpoint` tự xử lý auth của mình (token qua query param).

Thêm bypass trong `TokenAuthMiddleware.__call__`:

```python
path = scope.get("path", "")
if path.startswith("/events/"):
    await self.app(scope, receive, send)
    return
```

---

## Bước 4 — `agent_approve` MCP tool

Thêm vào `app/tools/autonomous_agent.py`:

```python
@mcp.tool(
    name="agent_approve",
    description=(
        "Approve a pending risky action for an assisted-autonomous goal. "
        "Call this after the user explicitly confirms they want to proceed. "
        "Returns immediately if no approval is pending."
    ),
)
def agent_approve(goal_id: str) -> dict:
    try:
        goal = _load_goal(goal_id)
        if not event_bus.pending_approval(goal_id):
            return {
                **_summarize_goal(goal),
                "ok": False,
                "message": "No pending approval for this goal.",
            }
        event_bus.resolve_approval(goal_id, approved=True)
        _append_event(goal_id, {"kind": "approval_resolved", "via": "mcp_tool"})
        log_audit_event("AGENT_APPROVED", {"goal_id": goal_id})
        return {
            **_summarize_goal(goal),
            "ok": True,
            "message": "Approval granted. agent_goal_start will resume.",
        }
    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="agent_reject",
    description="Reject a pending risky action and cancel the goal.",
)
def agent_reject(goal_id: str) -> dict:
    try:
        goal = _load_goal(goal_id)
        event_bus.resolve_approval(goal_id, approved=False)
        goal["status"] = "cancelled"
        _save_goal(goal)
        _append_event(goal_id, {"kind": "approval_rejected", "via": "mcp_tool"})
        log_audit_event("AGENT_REJECTED", {"goal_id": goal_id})
        return {**_summarize_goal(goal), "ok": True, "message": "Goal cancelled."}
    except Exception as e:
        return format_error_response(e)
```

`agent_reject` cần thiết vì nếu user nói "không, dừng lại" trong chat, GPT cần có tool để cancel thay vì `agent_goal_start` timeout sau 60 giây.

---

## Bước 5 — Wire `agent_approve` import vào `main.py`

`agent_approve` và `agent_reject` được định nghĩa trong `autonomous_agent.py` và tự register qua `@mcp.tool` — không cần thêm import riêng nếu `app.tools.autonomous_agent` đã được import trong `main.py` khi `ENABLE_ADVANCED_TOOLS=true`. Kiểm tra lại để chắc.

---

## Flow hoàn chỉnh sau Phase 3

```
User: "solve pwn challenge này"
GPT: agent_goal_create(objective="pwn: ...", cwd="~/Workspace/chall")
     → goal_id = "goal_abc123"
GPT: agent_goal_start(goal_id="goal_abc123")
     → loop bắt đầu: tool_status → recon → gadgets → ...
     → gặp risky action (ví dụ: sudo install)
     → agent_step returns needs_approval, loop pause, await Future (60s)

GPT → User: "Agent cần approve để chạy lệnh X. Gọi agent_approve để tiếp tục,
             hoặc xem live log tại: https://tunnel.trycloudflare.com/events/goal_abc123?token=..."

[Browser tab]: GET /events/goal_abc123?token=... → SSE stream hiện events real-time

User: "ok approve đi"
GPT: agent_approve(goal_id="goal_abc123")
     → resolve_approval(True) → Future resolved → agent_step tiếp tục
     → loop resume, chạy nốt các bước còn lại
     → complete hoặc blocked khi hết budget
```

---

## Checklist implement theo thứ tự

```
[ ] 0.1  Xóa token query param khỏi TokenAuthMiddleware (toàn bộ)
[ ] 0.2  Fix get_event_loop → get_running_loop trong event_bus.py
[ ] 0.3  git rm -r --cached logs/ && commit
[ ] 1    Refactor event_bus.py: xóa WebSocket section
[ ] 2    Tạo app/sse_events.py
[ ] 3    Mount sse_route trong patched_http_app, thêm bypass trong TokenAuthMiddleware
[ ] 4    Thêm agent_approve + agent_reject vào autonomous_agent.py
[ ] 5    Verify import chain trong main.py
[ ] 6    Test thủ công:
         - curl -N "http://localhost:8000/events/goal_xyz?token=..." → SSE stream
         - agent_goal_start → gặp risky → agent_approve → resume
         - agent_reject → goal cancelled
```

---

## Các rủi ro cần lưu ý

**Cloudflare tunnel timeout SSE connection** — Cloudflare free tunnel có idle timeout ~100 giây. Heartbeat 15 giây trong `sse_events_endpoint` (`": heartbeat\n\n"`) giải quyết được.

**`agent_goal_start` là `async def` nhưng chạy trong FastMCP thread pool** — nếu FastMCP gọi async tool trong event loop đúng cách thì `await asyncio.wait_for(fut, timeout=60)` hoạt động. Cần test thực tế với `fastmcp==3.4.0` vì behavior phụ thuộc vào cách FastMCP dispatch async tools.

**Multiple subscriber cùng goal** — `event_bus` dùng `Set[Queue]`, nhiều browser tab có thể subscribe cùng lúc mà không conflict. Không cần xử lý thêm.
