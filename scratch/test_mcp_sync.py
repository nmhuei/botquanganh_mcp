import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("GATEWAY_TOKEN", "change-this-to-a-long-random-secret")

url = "http://127.0.0.1:8000/mcp"

# 1. Probe to obtain session ID
print("[*] Probing local HTTP MCP endpoint...")
r_initial = httpx.get(url, headers={"Accept": "application/json, text/event-stream"})
session_id = r_initial.headers.get("mcp-session-id")
print(f"[+] Got session ID: {session_id}")

def send_mcp_request(method, params, req_id=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params
    }
    if req_id is not None:
        payload["id"] = req_id
        
    headers = {
        "Accept": "application/json, text/event-stream",
        "mcp-session-id": session_id
    }
    
    # We send the POST request and read the streaming response body
    res = httpx.post(url, json=payload, headers=headers, timeout=10.0)
    print(f"\n[POST {method}] Status: {res.status_code}")
    print(f"[POST {method}] Raw Response Body:")
    print(res.text)
    
    # Parse the JSON-RPC response from the SSE format
    for line in res.text.split("\n"):
        if line.startswith("data:"):
            data_val = line[5:].strip()
            try:
                return json.loads(data_val)
            except Exception:
                pass
    return None

# 2. Handshake Phase 1: Initialize
print("\n--- Handshake Phase 1: Sending initialize ---")
init_resp = send_mcp_request("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "1.0.0"}
}, req_id=100)
print(f"[Parsed Response]: {json.dumps(init_resp, indent=2)}")

# 3. Handshake Phase 2: Initialized
print("\n--- Handshake Phase 2: Sending initialized notification ---")
init_notify_resp = send_mcp_request("notifications/initialized", {})
print(f"[Parsed Response]: {init_notify_resp}")

# 4. Action Phase: Call tools/list
print("\n--- Action Phase: Listing tools ---")
list_resp = send_mcp_request("tools/list", {}, req_id=2)
print(f"[Parsed Response]: {json.dumps(list_resp, indent=2)}")

# 5. Action Phase: Call health_check
print("\n--- Action Phase: Calling health_check ---")
health_resp = send_mcp_request("tools/call", {
    "name": "health_check",
    "arguments": {}
}, req_id=3)

print(f"[Parsed Response]: {json.dumps(health_resp, indent=2)}")
