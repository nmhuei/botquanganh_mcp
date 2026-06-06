import sys
import os
import json
import httpx
import time

# Remote Cloudflare Tunnel URL
TUNNEL_URL = "https://liable-subtle-relocation-warning.trycloudflare.com/mcp"

# Shared session ID and state
session_id = None
created_workspace_id = None
created_run_id = None
created_artifact_id = None
rerun_id = None

# Track test statuses
tests_results = {}

def get_session():
    global session_id
    print("[*] Contacting remote MCP endpoint to obtain session ID...")
    try:
        r = httpx.get(TUNNEL_URL, headers={"Accept": "application/json, text/event-stream"})
        session_id = r.headers.get("mcp-session-id")
        if not session_id:
            print(f"[-] Failed to obtain session ID. Headers: {dict(r.headers)}, Status: {r.status_code}")
            sys.exit(1)
        print(f"[+] Session ID established: {session_id}")
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        sys.exit(1)

def send_rpc_request(method, params, req_id=999):
    headers = {
        "Accept": "application/json, text/event-stream",
        "mcp-session-id": session_id
    }
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": req_id
    }
    try:
        r = httpx.post(TUNNEL_URL, json=payload, headers=headers, timeout=45.0)
        if r.status_code not in (200, 202):
            return {"error": f"HTTP {r.status_code}: {r.text}"}
        
        # Parse SSE-like response data
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                data_val = line[5:].strip()
                try:
                    return json.loads(data_val)
                except Exception as pe:
                    return {"error": f"JSON Parse error: {pe}", "raw": line}
        return {"error": "No data: field found in SSE response"}
    except Exception as e:
        return {"error": f"Exception: {e}"}

def run_tool(name, arguments):
    print(f"\n==========================================")
    print(f"[*] Calling tool: {name}")
    print(f"[*] Arguments: {json.dumps(arguments, indent=2)}")
    print(f"==========================================")
    
    resp = send_rpc_request("tools/call", {
        "name": name,
        "arguments": arguments
    })
    
    if "error" in resp:
        print(f"[-] RPC Error: {resp['error']}")
        tests_results[name] = {"status": "FAILED", "error": resp["error"]}
        return None
    
    result_field = resp.get("result", {})
    is_error = result_field.get("isError", False)
    content = result_field.get("content", [])
    
    if is_error:
        print(f"[-] Tool reported failure: {content}")
        tests_results[name] = {"status": "FAILED", "details": content}
        return None
    
    # Try parsing structuredContent or just plain text from content
    structured = result_field.get("structuredContent")
    if not structured and content:
        for item in content:
            if item.get("type") == "text":
                try:
                    structured = json.loads(item.get("text"))
                except Exception:
                    structured = item.get("text")
                    
    if isinstance(structured, dict) and not structured.get("ok", True):
        print(f"[-] Tool returned ok=False: {structured.get('error')}")
        tests_results[name] = {"status": "FAILED", "response": structured}
        return None

    print(f"[+] Success. Response: {json.dumps(structured, indent=2)}")
    tests_results[name] = {"status": "PASSED", "response": structured}
    return structured

def main():
    global created_workspace_id, created_run_id, created_artifact_id, rerun_id
    
    get_session()
    
    # Handshake Step 1: Initialize
    print("\n[*] Sending handshake initialize request...")
    init_resp = send_rpc_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-suite", "version": "1.0.0"}
    }, req_id=1)
    if "error" in init_resp:
        print("[-] Handshake initialize failed:", init_resp["error"])
        sys.exit(1)
    print("[+] Handshake initialize response received.")
    
    # Handshake Step 2: Notifications/Initialized
    print("\n[*] Sending notifications/initialized...")
    send_rpc_request("notifications/initialized", {})
    time.sleep(0.5)
    
    # 1. health_check
    run_tool("health_check", {})
    
    # 2. get_capabilities
    run_tool("get_capabilities", {})
    
    # 3. get_runner_environments
    run_tool("get_runner_environments", {})
    
    # 4. check_target_allowed (Allowed public IP)
    run_tool("check_target_allowed", {"host": "8.8.8.8", "port": 53})
    
    # 5. check_target_allowed (Blocked private IP)
    res = send_rpc_request("tools/call", {
        "name": "check_target_allowed",
        "arguments": {"host": "127.0.0.1", "port": 80}
    })
    print("\n[*] check_target_allowed (127.0.0.1):", res)
    if res.get("result", {}).get("structuredContent", {}).get("allowed") is False:
        tests_results["check_target_allowed (Blocked Localhost)"] = {"status": "PASSED"}
    else:
        tests_results["check_target_allowed (Blocked Localhost)"] = {"status": "FAILED", "response": res}
        
    # 6. probe_target_from_runner
    run_tool("probe_target_from_runner", {
        "target": {"host": "8.8.8.8", "port": 53},
        "sandbox_failure_reason": "test fallback probe"
    })
    
    # 7. run_safe_smoke_test
    run_tool("run_safe_smoke_test", {})
    
    # 8. run_basic_python_solver
    run_tool("run_basic_python_solver", {
        "files": [{"name": "solve.py", "content": "import sys\nprint('Hello from basic solver!')\n"}],
        "entrypoint": "solve.py"
    })
    
    # 9. upload_artifact
    art = run_tool("upload_artifact", {
        "filename": "exploit.py",
        "content": "import sys\nimport os\nprint('Hello from advanced solver!')\nprint('TARGET_HOST:', os.getenv('TARGET_HOST'))\nprint('TARGET_PORT:', os.getenv('TARGET_PORT'))\n",
        "encoding": "text"
    })
    if art and art.get("ok"):
        created_artifact_id = art.get("artifact_id")
        
    # 10. validate_run_request
    run_tool("validate_run_request", {
        "target": {"host": "8.8.8.8", "port": 53},
        "sandbox_failure": {"reason": "dns lookup failure"},
        "local_validation": {"solved_locally": True, "summary": "solver passes locally"},
        "files": [{"name": "solve.py", "content": "print('valid')"}]
    })
    
    # 11. create_workspace
    ws = run_tool("create_workspace", {"label": "test-workspace-suite"})
    if ws and ws.get("ok"):
        created_workspace_id = ws.get("workspace_id")
        
    if created_workspace_id:
        # 12. upload_file_to_workspace
        run_tool("upload_file_to_workspace", {
            "workspace_id": created_workspace_id,
            "filename": "challenge.txt",
            "content": "Hello Workspace!",
            "encoding": "text"
        })
        
        # 13. list_workspace_files
        run_tool("list_workspace_files", {"workspace_id": created_workspace_id})
        
        # 14. read_workspace_file
        run_tool("read_workspace_file", {
            "workspace_id": created_workspace_id,
            "filename": "challenge.txt"
        })
        
        # 15. run_command (isolated shell inside container)
        run_tool("run_command", {
            "workspace_id": created_workspace_id,
            "command": "cat challenge.txt && echo 'Shell Executed'",
            "language": "python"
        })
        
        # 16. delete_workspace
        run_tool("delete_workspace", {"workspace_id": created_workspace_id})
        created_workspace_id = None
        
    # 17. run_solver_fallback (using the uploaded artifact)
    if created_artifact_id:
        fallback_payload = {
            "target": {"host": "8.8.8.8", "port": 53},
            "sandbox_failure": {"reason": "timeout in sandbox"},
            "local_validation": {"solved_locally": True, "summary": "worked on localhost"},
            "files": [{"name": "solve.py", "artifact_id": created_artifact_id}],
            "language": "python",
            "entrypoint": "solve.py"
        }
        res = run_tool("run_solver_fallback", fallback_payload)
        if res and res.get("ok"):
            created_run_id = res.get("run_id")
            
    # If fallback succeeded, run logging & tailing & rerun tests
    if created_run_id:
        # 18. list_recent_runs
        run_tool("list_recent_runs", {"limit": 5})
        
        # 19. get_run_summary
        run_tool("get_run_summary", {"run_id": created_run_id})
        
        # 20. get_run_log
        run_tool("get_run_log", {"run_id": created_run_id})
        
        # 21. get_run_stdout
        run_tool("get_run_stdout", {"run_id": created_run_id, "tail_lines": 5})
        
        # 22. get_run_stderr
        run_tool("get_run_stderr", {"run_id": created_run_id, "tail_lines": 5})
        
        # 23. tail_run_output
        run_tool("tail_run_output", {"run_id": created_run_id, "tail_lines": 5})
        
        # 24. rerun_run (Patching run details)
        rerun = run_tool("rerun_run", {
            "run_id": created_run_id,
            "patch": {
                "workspace": {
                    "files": [
                        {
                            "name": "solve.py",
                            "content": "print('Rerun complete!')\n"
                        }
                    ]
                },
                "execution": {
                    "timeout_seconds": 20
                }
            }
        })
        if rerun and rerun.get("ok"):
            rerun_id = rerun.get("run_id")
            
        # 25. delete_run
        run_tool("delete_run", {"run_id": created_run_id})
        if rerun_id:
            run_tool("delete_run", {"run_id": rerun_id})
            
    # Print summary of tests
    print("\n==========================================")
    print("           TEST RESULTS SUMMARY           ")
    print("==========================================")
    all_passed = True
    for t_name, t_info in tests_results.items():
        status = t_info.get("status")
        print(f"%-45s: %s" % (t_name, status))
        if status != "PASSED":
            all_passed = False
            
    if all_passed:
        print("\n[+++] ALL TESTS PASSED SUCCESSFULLY! [+++]")
        sys.exit(0)
    else:
        print("\n[-] SOME TESTS FAILED. CHECK LOGS ABOVE. [-]")
        sys.exit(1)

if __name__ == "__main__":
    main()
