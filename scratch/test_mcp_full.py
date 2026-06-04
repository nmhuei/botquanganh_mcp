import os
import json
import httpx
import threading
import time
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("GATEWAY_TOKEN", "change-this-to-a-long-random-secret")

url = "http://127.0.0.1:8000/mcp"

# 1. Obtain session ID
print("[*] Probing local HTTP MCP endpoint...")
r_initial = httpx.get(url, headers={"Accept": "application/json, text/event-stream"})
session_id = r_initial.headers.get("mcp-session-id")
print(f"[+] Got session ID: {session_id}")

stream_ready = threading.Event()
response_event = threading.Event()
latest_response = None
stream_closed = False

# 2. Spin up SSE stream reader thread using session ID
def read_stream():
    global latest_response, stream_closed
    headers = {
        "Accept": "application/json, text/event-stream",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-transform",
        "mcp-session-id": session_id
    }
    try:
        with httpx.stream("GET", url, headers=headers, timeout=20.0) as r:
            if r.status_code != 200:
                print(f"[-] GET stream failed: {r.status_code}")
                return
            print("[+] GET stream connected successfully.")
            stream_ready.set()
            
            for line in r.iter_lines():
                if stream_closed:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("data:"):
                    data_val = line_str[5:].strip()
                    print(f"[Stream Received]: {data_val}")
                    try:
                        payload = json.loads(data_val)
                        latest_response = payload
                        response_event.set()
                    except Exception:
                        pass
    except Exception as e:
        print(f"[-] Stream error: {e}")
    finally:
        stream_ready.set()
        response_event.set()

stream_thread = threading.Thread(target=read_stream, daemon=True)
stream_thread.start()

# Wait for stream connection
stream_ready.wait(timeout=5.0)

# Helper to send POST requests
def send_post(method, params, req_id=None):
    global latest_response
    latest_response = None
    response_event.clear()
    
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
    res = httpx.post(url, json=payload, headers=headers)
    print(f"[POST {method}] Status: {res.status_code}")
    return res

# 3. Send Initialize Request
print("\n--- Handshake Phase 1: Sending initialize ---")
send_post("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "1.0.0"}
}, req_id=100)

response_event.wait(timeout=5.0)
print(f"[+] initialize response: {json.dumps(latest_response, indent=2)}")

# 4. Send Initialized Notification
print("\n--- Handshake Phase 2: Sending initialized notification ---")
send_post("notifications/initialized", {})
time.sleep(0.5)

# 5. Call health_check tool call
print("\n--- Action Phase: Calling health_check tool ---")
send_post("tools/call", {
    "name": "health_check",
    "arguments": {}
}, req_id=1)


response_event.wait(timeout=5.0)
print(f"[+] tools/call response: {json.dumps(latest_response, indent=2)}")

stream_closed = True
