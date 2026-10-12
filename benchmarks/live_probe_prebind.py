"""Live probe testing pre-bind gating directly against the running server on port 18427."""

import json
import httpx

SERVER_URL = "http://127.0.0.1:18427/mcp"

client = httpx.Client(timeout=10.0)

# 1. Initialize
init_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}
r1 = client.post(SERVER_URL, json=init_payload, headers={"accept": "application/json, text/event-stream"})
print(f"Initialize status: {r1.status_code}")

# 2. Call server_info (Pre-bind: ALLOWED)
call_server_info = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "server_info",
        "arguments": {},
    },
}
r2 = client.post(SERVER_URL, json=call_server_info, headers={"accept": "application/json, text/event-stream"})
print(f"server_info: {r2.status_code}")
for line in r2.text.splitlines():
    if "result" in line:
        print(f"  -> {line[:120]}...")

# 3. Call workspace_context(action="note") before bind (Pre-bind: MUST BE BLOCKED E6)
call_note = {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
        "name": "workspace_context",
        "arguments": {"action": "note", "chat_id": "unbound-session-01", "note": "test"},
    },
}
r3 = client.post(SERVER_URL, json=call_note, headers={"accept": "application/json, text/event-stream"})
print(f"workspace_context(note) prebind: {r3.status_code}")
for line in r3.text.splitlines():
    if "result" in line or "error" in line:
        print(f"  -> {line}")

# 4. Call workspace_explore before bind (Pre-bind: MUST BE BLOCKED E6)
call_explore = {
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
        "name": "workspace_explore",
        "arguments": {"path": "/tmp", "action": "list", "chat_id": "unbound-session-01"},
    },
}
r4 = client.post(SERVER_URL, json=call_explore, headers={"accept": "application/json, text/event-stream"})
print(f"workspace_explore prebind: {r4.status_code}")
for line in r4.text.splitlines():
    if "result" in line or "error" in line:
        print(f"  -> {line[:120]}...")

# 5. Call workspace_context(action="bind") -> BIND SUCCEEDS
call_bind = {
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
        "name": "workspace_context",
        "arguments": {"action": "bind", "chat_id": "live-test-bound-01"},
    },
}
r5 = client.post(SERVER_URL, json=call_bind, headers={"accept": "application/json, text/event-stream"})
print(f"\nworkspace_context(bind): {r5.status_code}")
for line in r5.text.splitlines():
    if "result" in line:
        print(f"  -> {line[:120]}...")

# 6. Call workspace_context(action="note") after bind -> SUCCEEDS
call_note_after = {
    "jsonrpc": "2.0",
    "id": 6,
    "method": "tools/call",
    "params": {
        "name": "workspace_context",
        "arguments": {"action": "note", "chat_id": "live-test-bound-01", "note": "Live note after bind!"},
    },
}
r6 = client.post(SERVER_URL, json=call_note_after, headers={"accept": "application/json, text/event-stream"})
print(f"workspace_context(note) post-bind: {r6.status_code}")
for line in r6.text.splitlines():
    if "result" in line:
        print(f"  -> {line[:120]}...")

