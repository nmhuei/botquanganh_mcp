import json, sys

def verify(ws):
    try:
        with open(f"{ws}/solution.json") as f:
            d = json.load(f)
        assert d.get("status") == "solved"
        assert d.get("backdoor_pid") == 4922, f"Wrong backdoor_pid: {d.get('backdoor_pid')}"
        assert d.get("parent_daemon_pid") == 4921, f"Wrong daemon pid: {d.get('parent_daemon_pid')}"
        assert d.get("dropper_pid") == 3410, f"Wrong dropper pid: {d.get('dropper_pid')}"
        assert d.get("flag") == "FLAG{intercode_process_tree_audited_5192}", f"Wrong flag: {d.get('flag')}"
        print("VERIFY_SUCCESS: intercode_bash_04 passed 100%.")
        return True
    except Exception as e:
        print(f"VERIFY_FAIL: {e}")
        return False

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(0 if verify(p) else 1)
