import httpx

url = "http://127.0.0.1:8000/sse"
print(f"[*] Fetching SSE stream from: {url}")

try:
    with httpx.stream("GET", url, timeout=10.0) as r:
        print(f"[+] Connected! Status: {r.status_code}")
        count = 0
        for line in r.iter_lines():
            print(f"LINE {count}: {repr(line)}")
            count += 1
            if count > 15:
                break
except Exception as e:
    print(f"[-] Error: {e}")
