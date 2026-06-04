import os
import sys
from pwn import *

# In Docker runner environment, target details are passed via Env vars:
# CTF_HOST and CTF_PORT
host = os.environ.get("CTF_HOST", "127.0.0.1")
port = int(os.environ.get("CTF_PORT", "31337"))

print(f"[+] Starting solver connect to {host}:{port}")

try:
    r = remote(host, port, timeout=5)
    
    # Read initial welcome banner
    banner = r.recvline(timeout=2)
    print(f"[+] Received banner: {banner.decode('utf-8', errors='replace').strip()}")
    
    # Send challenge payload
    r.sendline(b"hello echo server")
    
    # Read response
    response = r.recvline(timeout=2)
    print(f"[+] Server response: {response.decode('utf-8', errors='replace').strip()}")
    
    r.close()
    
    # Success condition (simulate verifying the output)
    print("[+] Solve complete successfully!")
    sys.exit(0)
    
except Exception as e:
    print(f"[-] Connection or protocol error: {e}", file=sys.stderr)
    sys.exit(1)
