import sys
import os
import re
import json
import time
import httpx
import threading
from dotenv import load_dotenv

# Load env variables
load_dotenv()
token = os.getenv("GATEWAY_TOKEN", "change-this-to-a-long-random-secret")

if len(sys.argv) < 2:
    print("Usage: python3 test_sse_tunnel.py <tunnel_url_or_log_path>")
    sys.exit(1)

target = sys.argv[1]
url = ""

# 1. Resolve Cloudflare Tunnel URL
if target.startswith("http"):
    url = target
else:
    # Read from cloudflared logs
    time.sleep(4)  # Wait for cloudflared to boot
    if not os.path.exists(target):
        print(f"[-] Cloudflare log file {target} not found.")
        sys.exit(1)
        
    with open(target, "r") as f:
        log_content = f.read()
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", log_content)
        if match:
            url = match.group(0)
            print(f"[+] Discovered Tunnel URL: {url}")
        else:
            print("[-] Could not find TryCloudflare URL in log file. Logs:")
            print(log_content)
            sys.exit(1)

# 2. SSE Communication Client
sse_url = f"{url.rstrip('/')}/sse"
print(f"[*] Connecting to SSE stream: {sse_url}")

# Use a shared event and variable to coordinate threads
endpoint_ready_event = threading.Event()
message_endpoint_path = ""
tool_response_data = None
stream_closed = False

def read_sse_stream():
    global message_endpoint_path, tool_response_data, stream_closed
    try:
        with httpx.stream("GET", sse_url, timeout=20.0, follow_redirects=True) as r:
            if r.status_code != 200:
                print(f"[-] SSE GET failed with status: {r.status_code}")
                return
                
            print("[+] SSE stream successfully connected.")
            for line in r.iter_lines():
                if stream_closed:
                    break
                    
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Check for event declaration or data payload
                # Format:
                # event: endpoint
                # data: /messages?session_id=...
                #
                # Or JSON-RPC responses:
                # data: {"jsonrpc":"2.0","id":1,"result":...}
                
                if line_str.startswith("data:"):
                    data_val = line_str[5:].strip()
                    if "/messages" in data_val:
                        message_endpoint_path = data_val
                        endpoint_ready_event.set()
                    elif "jsonrpc" in data_val:
                        try:
                            payload = json.loads(data_val)
                            # Look for our request id=1
                            if payload.get("id") == 1 or "result" in payload:
                                tool_response_data = payload
                                break
                        except Exception as parse_err:
                            print(f"[!] Warning: failed to parse JSON data: {data_val}. Error: {parse_err}")
    except Exception as e:
        print(f"[-] SSE stream thread error: {e}")
    finally:
        endpoint_ready_event.set()  # Prevent lockups if connection dies

# Start SSE listener in a background thread
sse_thread = threading.Thread(target=read_sse_stream, daemon=True)
sse_thread.start()

# Wait for session registration message on the stream
print("[*] Waiting for message endpoint handshake...")
endpoint_ready_event.wait(timeout=10.0)

if not message_endpoint_path:
    print("[-] message_endpoint_path was not received. Aborting.")
    stream_closed = True
    sys.exit(1)

# 3. Post Tool Call Request
messages_url = f"{url.rstrip('/')}{message_endpoint_path}"
print(f"[*] Posting health_check tool call payload to: {messages_url}")

payload = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "health_check",
        "arguments": {
            "token": token
        }
    },
    "id": 1
}

try:
    post_res = httpx.post(messages_url, json=payload, timeout=5.0)
    print(f"[+] POST request completed. Status: {post_res.status_code}")
    if post_res.status_code not in (200, 202):
        print(f"[-] Tool call POST failed with body: {post_res.text}")
        stream_closed = True
        sys.exit(1)
except Exception as post_err:
    print(f"[-] Error posting to message endpoint: {post_err}")
    stream_closed = True
    sys.exit(1)

# 4. Await Tool response on the SSE stream
print("[*] Awaiting tool response on SSE stream...")
sse_thread.join(timeout=10.0)
stream_closed = True

if tool_response_data:
    print("\n[+++] SUCCESS! Received tool execution response from remote MCP over Cloudflare Tunnel [+++]")
    print(json.dumps(tool_response_data, indent=2))
    sys.exit(0)
else:
    print("[-] Did not receive tool response on the SSE stream within the timeout.")
    sys.exit(1)
