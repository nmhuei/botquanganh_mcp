import os
import sys

# Ensure the app folder is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force test configuration variables in environment
os.environ["GATEWAY_TOKEN"] = "debug-gateway-token-xyz-123"
os.environ["ALLOWED_TCP_TARGETS"] = "localhost:31337,127.0.0.1:31337,13.238.150.105:36970"
os.environ["BLOCK_PRIVATE_IPS"] = "false"  # False to verify loopback targets in tests

from app.tools.health import health_check
from app.tools.fallback import run_solver_fallback
from app.tools.probe import probe_target_from_runner

def test_health_checks():
    print("[*] Verification Stage 1: health_check")
    try:
        res = health_check()
        print(f"[+] SUCCESS: health_check completed. Result: {res}")
    except Exception as e:
        print(f"[-] FAILED: health_check error: {e}")
        return False
    return True

def test_probe_target():
    print("\n[*] Verification Stage 2: probe_target_from_runner")
    try:
        res = probe_target_from_runner(
            target={"host": "127.0.0.1", "port": 31337},
            sandbox_failure_reason="LLM sandbox could not connect to port 31337"
        )
        print(f"[+] SUCCESS: probe_target_from_runner completed. Reachable: {res['reachable']}, Duration: {res['duration_ms']}ms")
    except Exception as e:
        print(f"[-] FAILED: probe_target_from_runner error: {e}")
        return False
    return True

def test_run_solver_validations():
    print("\n[*] Verification Stage 3: run_solver_fallback input validation")
    
    # 1. Invalid sandbox failure (attempted=False)
    try:
        run_solver_fallback(
            target={"host": "127.0.0.1", "port": 31337},
            sandbox_failure={"attempted": False, "reason": ""},
            local_validation={"solved_locally": True, "summary": "works locally"},
            files=[{"path": "solve.py", "encoding": "text", "content": "print('hello')"}]
        )
        print("[-] FAILED: Server accepted a request with attempted=False sandbox failure.")
        return False
    except Exception as e:
        print(f"[+] SUCCESS: Server correctly blocked attempted=False. Error: {e}")

    # 2. Target not in allowlist
    try:
        run_solver_fallback(
            target={"host": "google.com", "port": 443},
            sandbox_failure={"attempted": True, "reason": "timeout"},
            local_validation={"solved_locally": True, "summary": "works locally"},
            files=[{"path": "solve.py", "encoding": "text", "content": "print('hello')"}]
        )
        print("[-] FAILED: Server allowed a non-allowlisted target host.")
        return False
    except Exception as e:
        print(f"[+] SUCCESS: Server blocked non-allowlisted target. Error: {e}")

    return True

if __name__ == "__main__":
    print("=== STARTING MCP PROGRAMMATIC DEBUGGING AND VERIFICATION ===")
    h_ok = test_health_checks()
    p_ok = test_probe_target()
    v_ok = test_run_solver_validations()
    
    if h_ok and p_ok and v_ok:
        print("\n[+++] ALL CORE MCP FUNCTIONALITIES AND SECURITY CHECKS ARE WORKING PERFECTLY! [+++]")
        sys.exit(0)
    else:
        print("\n[---] SOME MCP VERIFICATION CHECKS FAILED! [---]")
        sys.exit(1)
