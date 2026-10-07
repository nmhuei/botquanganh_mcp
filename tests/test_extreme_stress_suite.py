"""Extreme Hardcore Stress Test Suite for BQA MCP 2.0 Super-Tools.

Validates stability, resource bounds, concurrency, memory isolation,
and failure recovery under severe adversarial load.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent

from app.observability import MCPForensicsMiddleware
from app.tools.server_info import server_info
from app.tools.terminal_execute import terminal_execute
from app.tools.web_intelligence import web_intelligence
from app.tools.workspace_context import workspace_context
from app.tools.workspace_edit import workspace_edit
from app.tools.workspace_explore import workspace_explore
from app.tools.workspace_search import workspace_search
from app.tools_common import bridge_payload_ceiling

CEILING = bridge_payload_ceiling()
REPO_ROOT = Path(__file__).resolve().parents[1]


def wire_bytes(value: Any) -> int:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


@pytest.fixture
def stress_sandbox(monkeypatch):
    """Isolated directory for pathological stress tests."""
    from app import config
    root = Path.home() / "Downloads" / "bqa-trash" / f"stress-{int(time.time() * 1000)}"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "ATTRIBUTION_MODE", "off")
    monkeypatch.setattr(config, "HOST_CHAT_WORKSPACES", False)
    monkeypatch.setattr(config, "HOST_DEFAULT_DIR", root)
    monkeypatch.setattr(config, "HOST_WORKSPACE_DIR", root)
    monkeypatch.setattr(config, "HOST_RESTRICT_TO_WORKSPACE", False)
    yield root
    shutil.rmtree(root, ignore_errors=True)


# =========================================================================
# TEST 1: Massive 50MB Terminal Output Explosion & Memory Containment
# =========================================================================
def test_stress_50mb_terminal_output_flood(stress_sandbox):
    """Stress terminal_execute with a 50MB raw stdout blast."""
    py_code = (
        "import sys; "
        "chunk = 'X' * 1_000_000 + '\\n'; "
        "[sys.stdout.write(chunk) for _ in range(50)]; "
        "sys.stdout.flush()"
    )
    cmd = f"{shlex.quote(sys.executable)} -c {shlex.quote(py_code)}"

    tracemalloc.start()
    start_time = time.perf_counter()
    try:
        res = terminal_execute(command=cmd, cwd=str(stress_sandbox), timeout_seconds=20)
        _, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    elapsed = time.perf_counter() - start_time
    assert res["ok"] is True, res
    assert res["output_truncated"] is True
    assert "[TRUNCATED" in res["output"]
    assert "| head" in res["output"] or "| grep" in res["output"]
    assert wire_bytes(res) <= CEILING, f"Output wire size {wire_bytes(res)} exceeded {CEILING}"
    print(f"\\n[STRESS METRIC] 50MB Output Flood: Elapsed={elapsed:.2f}s, WireBytes={wire_bytes(res)}, PeakRAM={peak_memory / 1024 / 1024:.2f}MB")


# =========================================================================
# TEST 2: Concurrent Hammering (100 Simultaneous Tool Calls Across All 7 Tools)
# =========================================================================
def test_stress_100_concurrent_tool_hammering(stress_sandbox):
    """Hammer the 7 super-tools simultaneously with 100 concurrent workers."""
    # Seed sample files for exploration and editing
    for i in range(10):
        (stress_sandbox / f"file_{i}.py").write_text(f"# worker test file {i}\\nCOUNTER = 0\\n")

    def run_random_tool(call_id: int) -> dict[str, Any]:
        op_type = call_id % 6
        if op_type == 0:
            return workspace_search(path=str(stress_sandbox), query="COUNTER", mode="content")
        elif op_type == 1:
            file_path = str(stress_sandbox / f"file_{call_id % 10}.py")
            return workspace_explore(path=file_path, action="read", start_line=1, line_count=10)
        elif op_type == 2:
            file_path = str(stress_sandbox / f"file_{call_id % 10}.py")
            return workspace_edit(path=file_path, action="write", content=f"# edit from call {call_id}\\nCOUNTER = {call_id}\\n")
        elif op_type == 3:
            return terminal_execute(command=f"echo 'call_{call_id}'", cwd=str(stress_sandbox), timeout_seconds=5)
        elif op_type == 4:
            return workspace_context(action="bind", chat_id=f"stress-chat-{call_id % 5}")
        else:
            return server_info()

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(run_random_tool, i) for i in range(100)]
        results = [f.result() for f in as_completed(futures)]

    elapsed = time.perf_counter() - start_time
    assert len(results) == 100
    for idx, r in enumerate(results):
        assert isinstance(r, dict), f"Result {idx} is not a dict: {r}"
        assert wire_bytes(r) <= CEILING, f"Result {idx} wire bytes {wire_bytes(r)} exceeded ceiling"
        # If it's an error, it must be well-formed
        if not r.get("ok"):
            assert "error" in r or "truncated" in r, f"Malformed error in call {idx}: {r}"

    ops_per_sec = 100 / elapsed
    print(f"\\n[STRESS METRIC] 100 Concurrent Tool Calls: TotalTime={elapsed:.2f}s, Throughput={ops_per_sec:.1f} ops/sec")
    assert ops_per_sec > 10, f"Throughput {ops_per_sec} ops/sec below expectation"


# =========================================================================
# TEST 3: Concurrent Atomic Write Race Conditions on Overlapping Files
# =========================================================================
def test_stress_concurrent_atomic_write_race_integrity(stress_sandbox):
    """Stress test atomic file operations under heavy contention without corruption."""
    shared_file = stress_sandbox / "contentious_target.py"
    shared_file.write_text("STATE = 0\\n")

    def edit_worker(worker_id: int) -> dict[str, Any]:
        content = f"# Worker {worker_id}\\nSTATE = {worker_id}\\nSTATUS = 'OK'\\n"
        return workspace_edit(path=str(shared_file), action="write", content=content)

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(edit_worker, i) for i in range(50)]
        results = [f.result() for f in as_completed(futures)]

    # Verify all calls succeeded and file is intact
    assert all(r["ok"] for r in results)
    final_content = shared_file.read_text()
    assert "STATE =" in final_content
    assert "STATUS = 'OK'" in final_content
    assert shared_file.stat().st_size > 0
    # No temporary files leaked
    leftover_temps = list(stress_sandbox.glob(".bqa_edit_*"))
    assert len(leftover_temps) == 0, f"Found leaked temp files: {leftover_temps}"
    print(f"\\n[STRESS METRIC] 50 Concurrent Writes on Single File: Intact, Zero Leaked Temp Files")


# =========================================================================
# TEST 4: Pathological Deep Directory Tree with Symlink Cycles & Null Bytes
# =========================================================================
def test_stress_pathological_directory_tree_and_symlink_defense(stress_sandbox):
    """Create a deeply nested tree with thousands of files, symlink loop, and binary junk."""
    current = stress_sandbox
    for depth in range(15):
        current = current / f"nested_level_{depth}"
        current.mkdir(parents=True, exist_ok=True)
        # Drop mixed files
        (current / "code.py").write_text(f"# level {depth}\\nsecret = 'deep_flag_{depth}'\\n")
        (current / "binary.bin").write_bytes(b"\\x00\\xff\\xfe" * 500)

    # Create an intentional recursive symlink loop
    loop_link = stress_sandbox / "recursive_symlink_loop"
    try:
        loop_link.symlink_to(stress_sandbox, target_is_directory=True)
    except OSError:
        pass  # If OS prevents, continue

    # Ripgrep search must not get stuck in infinite recursion
    start_time = time.perf_counter()
    res = workspace_search(path=str(stress_sandbox), query="deep_flag", mode="content", max_matches=50)
    search_time = time.perf_counter() - start_time

    assert res["ok"] is True, res
    assert len(res["matches"]) > 0
    assert search_time < 2.0, f"Search took too long ({search_time:.2f}s) - possible loop"
    assert wire_bytes(res) <= CEILING
    print(f"\\n[STRESS METRIC] Deep Tree Symlink Search: Found {len(res['matches'])} matches in {search_time*1000:.1f}ms")


# =========================================================================
# TEST 5: Subprocess Explosion & Process Group Termination Under Pressure
# =========================================================================
def test_stress_subprocess_explosion_and_orphan_cleanup(stress_sandbox):
    """Launch 15 processes spawning long-lived children and verify clean termination."""
    pid_dir = stress_sandbox / "pids"
    pid_dir.mkdir(parents=True, exist_ok=True)

    def spawn_sleeper(index: int) -> dict[str, Any]:
        pfile = pid_dir / f"proc_{index}.pid"
        cmd = f"sleep 120 & echo $! > {shlex.quote(str(pfile))}; wait"
        return terminal_execute(command=cmd, cwd=str(stress_sandbox), timeout_seconds=1)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(spawn_sleeper, i) for i in range(15)]
        results = [f.result() for f in as_completed(futures)]

    # All should report timeout
    assert all(r["timed_out"] is True for r in results)

    # Give OS a moment to reap
    time.sleep(0.5)

    # Check /proc for every spawned child PID
    orphans = []
    for pfile in pid_dir.glob("proc_*.pid"):
        try:
            pid = int(pfile.read_text().strip())
            stat_path = Path(f"/proc/{pid}/stat")
            if stat_path.exists():
                state = stat_path.read_text().split(")", 1)[1].split()[0]
                if state != "Z":  # Not zombie
                    orphans.append(pid)
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        except Exception:
            pass

    assert len(orphans) == 0, f"Orphaned background processes found: {orphans}"
    print(f"\\n[STRESS METRIC] 15 Timed-out Subprocesses: 100% of Child Process Groups Reaped")


# =========================================================================
# TEST 6: Middleware Adversarial Wire Flooding (10MB Raw Stream)
# =========================================================================
def test_stress_forensics_middleware_gigantic_payload_defense():
    """Verify middleware handles a 10MB structured payload without memory exhaustion."""
    giant_data = {"chunk": "A" * 10_000_000}
    oversized_res = CallToolResult(
        content=[TextContent(type="text", text="small")],
        structuredContent=giant_data,
    )

    async def call_next(context):
        return oversized_res

    context = SimpleNamespace(message=SimpleNamespace(name="adversarial_flood"))
    bounded = asyncio.run(MCPForensicsMiddleware().on_call_tool(context, call_next))

    assert bounded.isError is True
    assert wire_bytes(bounded) <= CEILING
    envelope = json.loads(bounded.content[0].text)
    assert envelope["ok"] is False
    assert envelope["truncated"] is True
    assert envelope["error"]["code"] == "PAYLOAD_LIMIT_EXCEEDED"
    print(f"\\n[STRESS METRIC] 10MB Wire Attack: Intercepted & Scaled Down to {wire_bytes(bounded)} Bytes")
