import sys
import os
import re
import json
import time
import httpx
from dotenv import load_dotenv

# Load env variables
load_dotenv()
token = os.getenv("GATEWAY_TOKEN", "change-this-to-a-long-random-secret")

if len(sys.argv) < 2:
    print("Usage: python3 test_http_tunnel.py <tunnel_log_path>")
    sys.exit(1)

log_path = sys.argv[1]
url = ""

# 1. Resolve Cloudflare Tunnel URL
time.sleep(2)
if not os.path.exists(log_path):
    print(f"[-] Cloudflare log file {log_path} not found.")
    sys.exit(1)
    
with open(log_path, "r") as f:
    log_content = f.read()
    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", log_content)
    if match:
        url = match.group(0)
        print(f"[+] Discovered Tunnel URL: {url}")
    else:
        print("[-] Could not find TryCloudflare URL in log file.")
        sys.exit(1)

mcp_url = f"{url.rstrip('/')}/mcp"

# 2. Get session ID by performing a GET request
print("[*] Probing /mcp to obtain session ID...")
initial_res = httpx.get(
    mcp_url, 
    headers={"Accept": "application/json, text/event-stream"}
)
session_id = initial_res.headers.get("mcp-session-id")
if not session_id:
    print(f"[-] Did not receive mcp-session-id in headers. Response status: {initial_res.status_code}")
    sys.exit(1)

print(f"[+] Obtained session ID: {session_id}")

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
    res = httpx.post(mcp_url, json=payload, headers=headers, timeout=15.0)
    print(f"[POST {method}] Status: {res.status_code}")
    
    # Parse the JSON-RPC response from the SSE format
    for line in res.text.split("\n"):
        if line.startswith("data:"):
            data_val = line[5:].strip()
            try:
                return json.loads(data_val)
            except Exception:
                pass
    return None

# 3. Handshake Phase 1: Initialize
print("\n--- Handshake Phase 1: Sending initialize ---")
init_resp = send_mcp_request("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "1.0.0"}
}, req_id=100)

if not init_resp or "result" not in init_resp:
    print(f"[-] Handshake Phase 1 Failed. Response: {init_resp}")
    sys.exit(1)
print("[+] initialize handshake successful.")

# 4. Handshake Phase 2: Initialized
print("\n--- Handshake Phase 2: Sending initialized notification ---")
send_mcp_request("notifications/initialized", {})

# 5. Call health_check tool call
print("\n--- Action Phase: Calling health_check tool ---")
tool_resp = send_mcp_request("tools/call", {
    "name": "health_check",
    "arguments": {}
}, req_id=3)


if tool_resp and "result" in tool_resp:
    print("\n[+++] SUCCESS! Received tool execution response from remote MCP over Cloudflare Tunnel [+++]")
    print(json.dumps(tool_resp, indent=2))
    sys.exit(0)
else:
    print(f"[-] Tool call failed. Response: {tool_resp}")
    sys.exit(1)
