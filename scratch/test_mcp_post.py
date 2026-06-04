import os
import httpx
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("GATEWAY_TOKEN", "change-this-to-a-long-random-secret")

url = "http://127.0.0.1:8000/mcp"
print(f"[*] Probing local HTTP MCP endpoint: {url}")

# 1. Obtain session ID
r_initial = httpx.get(url, headers={"Accept": "application/json, text/event-stream"})
session_id = r_initial.headers.get("mcp-session-id")
print(f"[+] Got session ID: {session_id}")

# 2. POST tool call with session ID and inspect response body
payload = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "health_check",
        "arguments": {}
    },
    "id": 1
}

headers = {
    "Accept": "application/json, text/event-stream",
    "mcp-session-id": session_id
}

print(f"[*] Posting health_check to {url}...")
res = httpx.post(url, json=payload, headers=headers, timeout=5.0)

print(f"[+] POST Status Code: {res.status_code}")
print("[+] POST Response Headers:")
for k, v in res.headers.items():
    print(f"  {k}: {v}")
print("[+] POST Response Body:")
print(res.text)
