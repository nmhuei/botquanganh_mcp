import sys
import json
import asyncio
import httpx

async def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    print(f"Connecting to SSE endpoint: {base_url} ...")
    
    async with httpx.AsyncClient() as client:
        # 1. Connect to SSE GET stream
        # We need to run the stream in a task so we can read from it concurrently while sending POST requests
        endpoint_url = None
        
        # We will use a Future to pass the endpoint URL from the reader task to the main flow
        endpoint_future = asyncio.get_running_loop().create_future()
        # We will use a dict to store futures for each request ID so we can await responses
        response_futures = {}
        
        async def read_stream():
            nonlocal endpoint_url
            try:
                async with client.stream("GET", base_url, headers={"accept": "text/event-stream"}, timeout=60.0) as response:
                    if response.status_code != 200:
                        print(f"Stream connection failed: {response.status_code}")
                        endpoint_future.set_exception(Exception(f"Status {response.status_code}"))
                        return
                        
                    event_type = None
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data_val = line.split(":", 1)[1].strip()
                            if event_type == "endpoint":
                                endpoint_url = data_val
                                if not endpoint_future.done():
                                    endpoint_future.set_result(endpoint_url)
                            elif event_type == "message":
                                # This is a JSON-RPC message
                                msg = json.loads(data_val)
                                print(f"\n[SSE Received Message]: {json.dumps(msg, indent=2)}")
                                msg_id = str(msg.get("id"))
                                if msg_id in response_futures:
                                    response_futures[msg_id].set_result(msg)
            except Exception as e:
                print(f"Error in stream reader: {e}")
                if not endpoint_future.done():
                    endpoint_future.set_exception(e)
        
        # Start reader task
        reader_task = asyncio.create_task(read_stream())
        
        try:
            # Wait for endpoint URL
            endpoint_url = await asyncio.wait_for(endpoint_future, timeout=10.0)
            print(f"Received endpoint path: {endpoint_url}")
            
            if endpoint_url.startswith("/"):
                from urllib.parse import urljoin
                post_url = urljoin(base_url, endpoint_url)
            else:
                post_url = endpoint_url
                
            print(f"POST endpoint URL: {post_url}")
            
            # Helper to send a request and await its response from the SSE stream
            async def send_request(method, params, req_id):
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params
                }
                fut = asyncio.get_running_loop().create_future()
                response_futures[req_id] = fut
                
                print(f"\n[POST Send Request]: {json.dumps(payload)}")
                res = await client.post(post_url, json=payload)
                if res.status_code != 202:
                    print(f"POST failed: {res.status_code}")
                    return None
                    
                # Wait for the response to arrive in the SSE stream
                response = await asyncio.wait_for(fut, timeout=10.0)
                return response

            # 2. Send initialize
            await send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                },
                "1"
            )
            
            # Send initialized notification
            initialized_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            print(f"\n[POST Send Notification]: {json.dumps(initialized_payload)}")
            await client.post(post_url, json=initialized_payload)
            await asyncio.sleep(1) # Settle initialized state
            
            # 3. Send tools/list
            list_res = await send_request("tools/list", {}, "2")
            if list_res:
                tools = [t["name"] for t in list_res.get("result", {}).get("tools", [])]
                print(f"\n[INFO] Available tools list parsed from result: {tools}")
                
            # 4. Call health_check tool
            await send_request(
                "tools/call",
                {
                    "name": "health_check",
                    "arguments": {}
                },
                "3"
            )
            
            print("\n[SUCCESS] E2E SSE Manual Test Completed successfully!")
            
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main())
