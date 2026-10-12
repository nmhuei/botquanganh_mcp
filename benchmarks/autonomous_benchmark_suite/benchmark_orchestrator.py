#!/usr/bin/env python3
"""
Autonomous Benchmark Orchestrator & Root Cause Analyzer (5 Workers)
Tracks Cybench, InterCode, and SWE-bench tasks until complete.
"""
import os
import sys
import time
import json
import shutil
import subprocess
from datetime import datetime

BASE_DIR = "/home/light/Downloads/bqa-trash/autonomous_benchmark_suite"
TASKS = [
    "cybench_net_01",
    "cybench_crypto_02",
    "cybench_rev_03",
    "intercode_bash_04",
    "swebench_patch_05"
]

def init_workspaces():
    print("[+] Initializing isolated workspaces for 5 workers...")
    for t in TASKS:
        src = f"{BASE_DIR}/tasks/{t}"
        dst = f"{BASE_DIR}/workspaces/{t}"
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        # Remove verifier from workspace so worker can't cheat
        if os.path.exists(f"{dst}/verify.py"):
            os.remove(f"{dst}/verify.py")
        print(f"  -> Workspace prepared: {dst}")

def analyze_root_cause(session_id, task_id, ws_path, err_msg=""):
    """Performs deep Root Cause Analysis by inspecting session logs and telemetry."""
    rca = {
        "task_id": task_id,
        "session_id": session_id,
        "error_message": err_msg,
        "root_cause_category": "UNKNOWN",
        "details": [],
        "remediation_applied": None
    }
    
    if not session_id:
        rca["root_cause_category"] = "DISPATCH_FAILED"
        rca["details"].append("Worker process exited before acquiring session ID.")
        return rca

    # Run gpt session log --events to get telemetry
    try:
        cmd = ["gpt", "session", "log", session_id, "--events"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw_events = res.stdout
        
        if "sse_interrupted" in raw_events:
            rca["root_cause_category"] = "SSE_INTERRUPTED"
            rca["details"].append("Stream terminated prematurely by provider / conduit wire.")
        elif "container.exec" in raw_events and "No such file" in raw_events:
            rca["root_cause_category"] = "CONTAINER_PATH_CONFUSION"
            rca["details"].append("Model fell back to cloud container execution instead of host tool.")
        elif "list_resources" in raw_events and "terminal_execute" not in raw_events and "workspace_edit" not in raw_events:
            rca["root_cause_category"] = "TOOL_DISCOVERY_BLINDNESS"
            rca["details"].append("Model did not discover filesystem/execution tools.")
        elif not os.path.exists(f"{ws_path}/solution.json"):
            rca["root_cause_category"] = "PREMATURE_TERMINATION"
            rca["details"].append("Model stopped without generating solution.json.")
        else:
            rca["root_cause_category"] = "ORACLE_VERIFICATION_MISMATCH"
            rca["details"].append("Model completed execution but produced incorrect output data.")
    except Exception as e:
        rca["details"].append(f"Failed to inspect telemetry: {e}")
        
    return rca

def verify_task(task_id, ws_path):
    """Executes the ground-truth verifier against the worker's workspace."""
    verifier_script = f"{BASE_DIR}/tasks/{task_id}/verify.py"
    if not os.path.exists(verifier_script):
        return False, "Verifier script missing"
        
    res = subprocess.run([sys.executable, verifier_script, ws_path], capture_output=True, text=True, timeout=30)
    passed = (res.returncode == 0)
    output = res.stdout.strip() if passed else (res.stderr.strip() or res.stdout.strip())
    return passed, output

def main():
    print("=" * 80)
    print("AUTONOMOUS 5-WORKER BENCHMARK ORCHESTRATOR")
    print("Benchmark Suite: Cybench (x3), InterCode (x1), SWE-bench (x1)")
    print("=" * 80)
    
    init_workspaces()
    
    workers = {}
    start_times = {}
    
    # Launch 5 workers in parallel with 3-second staggered start
    for idx, t in enumerate(TASKS):
        ws_path = f"{BASE_DIR}/workspaces/{t}"
        prompt = (
            f"solve {ws_path} Đọc kỹ TASK.md trong workspace của bạn. "
            f"Tự khảo sát các công cụ khả dụng của bạn trên hệ thống, phân tích bài toán, "
            f"thực thi các bước giải quyết, viết code/script cần thiết, tự kiểm chứng kết quả "
            f"và lưu kết quả vào solution.json theo đúng Definition of Done. "
            f"Tự chạy kiểm thử và khắc phục mọi lỗi phát sinh cho đến khi hoàn tất nhiệm vụ."
        )
        tag = f"bench-w{idx+1}-{t}"
        cmd = ["gpt", "run", "-t", tag, "-b", "br", "-p", prompt, "--json"]
        
        log_file = open(f"{BASE_DIR}/reports/worker_{t}.log", "w")
        print(f"[*] Launching Worker {idx+1} [{t}] (tag={tag})...")
        p = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, text=True)
        workers[t] = {
            "proc": p,
            "log_file": log_file,
            "ws_path": ws_path,
            "tag": tag,
            "session_id": None,
            "status": "RUNNING",
            "retries": 0,
            "rca": None,
            "verified": False,
            "verify_output": "",
            "start_time": time.time(),
            "end_time": None
        }
        time.sleep(3) # Staggered startup to avoid concurrent wire handshake spikes
        
    print(f"\n[+] All 5 workers dispatched. Actively monitoring execution and self-healing...")
    
    active_count = len(workers)
    check_interval = 5
    
    while active_count > 0:
        for t, w in workers.items():
            if w["status"] != "RUNNING":
                continue
                
            poll = w["proc"].poll()
            if poll is not None:
                # Worker finished
                w["end_time"] = time.time()
                w["log_file"].close()
                duration = round(w["end_time"] - w["start_time"], 2)
                
                # Extract session_id from worker log
                try:
                    with open(f"{BASE_DIR}/reports/worker_{t}.log") as f:
                        log_content = f.read()
                    for line in log_content.splitlines():
                        if '"session_id"' in line:
                            data = json.loads(line)
                            w["session_id"] = data.get("session_id")
                            break
                        elif "sess_" in line:
                            import re
                            m = re.search(r"sess_[a-f0-9]+", line)
                            if m:
                                w["session_id"] = m.group(0)
                                break
                except Exception:
                    pass

                print(f"\n[!] Worker [{t}] finished in {duration}s (exit_code={poll}). Verifying solution...")
                
                # Verify solution
                passed, v_out = verify_task(t, w["ws_path"])
                w["verified"] = passed
                w["verify_output"] = v_out
                
                if passed:
                    w["status"] = "PASSED"
                    print(f"  [PASS@1 SUCCESS] Worker [{t}] verified 100%! Output: {v_out}")
                else:
                    # Root Cause Analysis
                    print(f"  [VERIFY FAIL] Worker [{t}] failed verification. Running RCA...")
                    rca = analyze_root_cause(w["session_id"], t, w["ws_path"], v_out)
                    w["rca"] = rca
                    print(f"  -> RCA Category: {rca['root_cause_category']}")
                    for d in rca["details"]:
                        print(f"     * {d}")
                        
                    # Self-Healing Retry (Allow 1 corrective turn if session exists)
                    if w["retries"] < 1 and w["session_id"]:
                        print(f"  -> Initiating Self-Healing Retry for [{t}] (session={w['session_id']})...")
                        w["retries"] += 1
                        retry_prompt = (
                            f"Kết quả kiểm thử chưa đạt yêu cầu: {v_out}. "
                            f"Hãy kiểm tra lại workspace của bạn, xác định nguyên nhân gốc rễ, "
                            f"sửa lại code/dữ liệu và cập nhật lại solution.json hoàn chỉnh."
                        )
                        retry_log = open(f"{BASE_DIR}/reports/worker_{t}_retry.log", "w")
                        retry_cmd = ["gpt", "run", "--resume-session", w["session_id"], "-b", "br", "-p", retry_prompt, "--json"]
                        p_retry = subprocess.Popen(retry_cmd, stdout=retry_log, stderr=subprocess.STDOUT, text=True)
                        w["proc"] = p_retry
                        w["log_file"] = retry_log
                        w["status"] = "RUNNING"
                        continue
                    else:
                        w["status"] = "FAILED"
                        print(f"  [FINAL FAIL] Worker [{t}] failed after retries.")
                
                active_count = sum(1 for x in workers.values() if x["status"] == "RUNNING")
                print(f"[*] Active workers remaining: {active_count}/5")
                
        time.sleep(check_interval)
        
    print("\n" + "=" * 80)
    print("BENCHMARK EXECUTION COMPLETED")
    print("=" * 80)
    
    # Generate final report
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_tasks": len(TASKS),
        "passed_count": sum(1 for w in workers.values() if w["status"] == "PASSED"),
        "failed_count": sum(1 for w in workers.values() if w["status"] == "FAILED"),
        "tasks": {}
    }
    for t, w in workers.items():
        summary["tasks"][t] = {
            "status": w["status"],
            "session_id": w["session_id"],
            "duration_seconds": round((w["end_time"] or time.time()) - w["start_time"], 2),
            "retries": w["retries"],
            "verify_output": w["verify_output"],
            "rca": w["rca"]
        }
        
    with open(f"{BASE_DIR}/reports/benchmark_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        
    # Generate Markdown Report
    md_lines = [
        "# BÁO CÁO KẾT QUẢ BENCHMARK 5 WORKERS TỰ TRỊ (CYBENCH, INTERCODE, SWEBENCH)",
        "",
        f"- **Thời gian thực hiện:** {summary['timestamp']}",
        f"- **Tổng số tasks:** {summary['total_tasks']}",
        f"- **Kết quả:** **{summary['passed_count']}/{summary['total_tasks']} PASSED** (Pass@1: {round(summary['passed_count']/summary['total_tasks']*100, 1)}%)",
        "",
        "## Bảng Chi Tiết Kết Quả Từng Worker",
        "",
        "| Worker / Task | Mảng Benchmark | Trạng thái | Thời gian | Retries | Root Cause Analysis (nếu lỗi) |",
        "|---|---|:---:|:---:|:---:|---|"
    ]
    for t, data in summary["tasks"].items():
        st = "✅ **PASS**" if data["status"] == "PASSED" else "❌ **FAIL**"
        dur = f"{data['duration_seconds']}s"
        rca_str = data["rca"]["root_cause_category"] if data["rca"] else "N/A (Passed)"
        md_lines.append(f"| `{t}` | {t.split('_')[0].upper()} | {st} | {dur} | {data['retries']} | {rca_str} |")
        
    md_lines.append("")
    md_lines.append("## Phân Tích Nguyên Nhân Gốc Rễ (RCA Chi Tiết)")
    for t, data in summary["tasks"].items():
        if data["rca"]:
            md_lines.append(f"### Task `{t}`")
            md_lines.append(f"- **Category:** `{data['rca']['root_cause_category']}`")
            for detail in data['rca']['details']:
                md_lines.append(f"- {detail}")
                
    with open(f"{BASE_DIR}/reports/benchmark_report.md", "w") as f:
        f.write("\n".join(md_lines) + "\n")
        
    print(f"\n[+] Final reports generated at:")
    print(f"  -> {BASE_DIR}/reports/benchmark_summary.json")
    print(f"  -> {BASE_DIR}/reports/benchmark_report.md")

if __name__ == "__main__":
    main()
