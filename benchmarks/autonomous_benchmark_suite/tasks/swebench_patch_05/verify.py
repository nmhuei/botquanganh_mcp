import json, sys, subprocess

def verify(ws):
    try:
        # Run pytest
        res = subprocess.run(["pytest", "-q"], cwd=ws, env={"PYTHONPATH": f"{ws}/src", "PATH": sys.path[0] + ":/usr/bin:/bin"}, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"VERIFY_FAIL: Pytest failed:\n{res.stdout}\n{res.stderr}")
            return False
            
        with open(f"{ws}/solution.json") as f:
            d = json.load(f)
        assert d.get("status") == "solved"
        print(f"VERIFY_SUCCESS: swebench_patch_05 passed. Pytest output:\n{res.stdout}")
        return True
    except Exception as e:
        print(f"VERIFY_FAIL: {e}")
        return False

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(0 if verify(p) else 1)
