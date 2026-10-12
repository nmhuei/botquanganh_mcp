"""Benchmark execution latency for all 8 Super-Tools, with deep profiling of workspace_search."""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

# Setup environment for benchmark
BENCHMARK_DIR = Path("/home/light/Downloads/bqa-trash/benchmarks")
if BENCHMARK_DIR.exists():
    shutil.rmtree(BENCHMARK_DIR)
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

os.environ["ATTRIBUTION_MODE"] = "enforce"
os.environ["HOST_CHAT_WORKSPACES"] = "true"
os.environ["HOST_CHAT_ROOT"] = str(BENCHMARK_DIR / "workspaces")
os.environ["HOST_DEFAULT_DIR"] = str(BENCHMARK_DIR)
os.environ["HOST_WORKSPACE_DIR"] = str(BENCHMARK_DIR)

import app.config
app.config.ATTRIBUTION_MODE = "enforce"
app.config.HOST_CHAT_WORKSPACES = True
app.config.HOST_CHAT_ROOT = str(BENCHMARK_DIR / "workspaces")
app.config.HOST_DEFAULT_DIR = BENCHMARK_DIR
app.config.HOST_WORKSPACE_DIR = BENCHMARK_DIR

from app.tools.server_info import server_info
from app.tools.workspace_context import workspace_context
from app.tools.workspace_explore import workspace_explore
from app.tools.workspace_edit import workspace_edit
from app.tools.terminal_execute import terminal_execute
from app.tools.task import task
from app.tools.workspace_search import workspace_search
from app.task_manager import get_task_manager


def time_call(fn, *args, **kwargs):
    start = time.perf_counter()
    res = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return res, elapsed_ms


async def time_async_call(fn, *args, **kwargs):
    start = time.perf_counter()
    res = await fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return res, elapsed_ms


def main():
    print("================================================================")
    print("      BOTQUANGANH MCP 2.0 - LATENCY BENCHMARK REPORT           ")
    print("================================================================")
    results = {}

    # 1. server_info (Pre-bind allowed)
    res, dur = time_call(server_info)
    results["server_info"] = dur
    print(f"1. server_info: {dur:.2f} ms [ok: {res.get('ok')}]")

    # 2. workspace_context(action="list") (Pre-bind allowed)
    res, dur = time_call(workspace_context, action="list")
    results["workspace_context_list_prebind"] = dur
    print(f"2. workspace_context(action='list'): {dur:.2f} ms [ok: {res.get('ok')}]")

    # 3. workspace_context(action="bind")
    chat_id = "bench-chat-perf-01"
    res, dur = time_call(workspace_context, action="bind", chat_id=chat_id, label="benchmark")
    results["workspace_context_bind"] = dur
    ws_path = Path(res["workspace_path"])
    print(f"3. workspace_context(action='bind'): {dur:.2f} ms [ok: {res.get('ok')}, id: {chat_id}]")

    # 4. workspace_context operations
    res, dur = time_call(workspace_context, action="note", chat_id=chat_id, note="Performance benchmark in progress.")
    results["workspace_context_note"] = dur
    print(f"4a. workspace_context(action='note'): {dur:.2f} ms [ok: {res.get('ok')}]")

    res, dur = time_call(
        workspace_context,
        action="state",
        chat_id=chat_id,
        state_update={"objective": "Profile latency", "current_task": "Benchmarking all tools"},
    )
    results["workspace_context_state"] = dur
    print(f"4b. workspace_context(action='state'): {dur:.2f} ms [ok: {res.get('ok')}]")

    res, dur = time_call(
        workspace_context,
        action="hypotheses",
        chat_id=chat_id,
        hypothesis="Memory copy causes latency",
        hypothesis_result="rejected",
        do_not_retry=True,
        reason="Zero-copy fits ceiling safely",
    )
    results["workspace_context_hypotheses"] = dur
    print(f"4c. workspace_context(action='hypotheses'): {dur:.2f} ms [ok: {res.get('ok')}]")

    res, dur = time_call(workspace_context, action="resume", chat_id=chat_id)
    results["workspace_context_resume"] = dur
    print(f"4d. workspace_context(action='resume'): {dur:.2f} ms [ok: {res.get('ok')}]")

    # 5. workspace_edit
    sample_file = ws_path / "benchmark_test.py"
    res, dur = time_call(
        workspace_edit,
        path=str(sample_file),
        action="write",
        content="# Benchmark file\nVALUE = 42\nMESSAGE = 'Hello World'\n",
        chat_id=chat_id,
    )
    results["workspace_edit_write"] = dur
    print(f"5a. workspace_edit(action='write'): {dur:.2f} ms [ok: {res.get('ok')}]")

    res, dur = time_call(
        workspace_edit,
        path=str(sample_file),
        action="append",
        content="DEBUG_FLAG = True\n",
        chat_id=chat_id,
    )
    results["workspace_edit_append"] = dur
    print(f"5b. workspace_edit(action='append'): {dur:.2f} ms [ok: {res.get('ok')}]")

    res, dur = time_call(
        workspace_edit,
        path=str(sample_file),
        action="replace",
        old_text="VALUE = 42",
        new_text="VALUE = 100",
        chat_id=chat_id,
    )
    results["workspace_edit_replace"] = dur
    print(f"5c. workspace_edit(action='replace'): {dur:.2f} ms [ok: {res.get('ok')}]")

    # 6. workspace_explore
    res, dur = time_call(workspace_explore, path=str(ws_path), action="list", chat_id=chat_id)
    results["workspace_explore_list"] = dur
    print(f"6a. workspace_explore(action='list'): {dur:.2f} ms [ok: {res.get('ok')}, entries: {len(res.get('entries', []))}]")

    res, dur = time_call(
        workspace_explore,
        path=str(sample_file),
        action="read",
        start_line=1,
        line_count=10,
        chat_id=chat_id,
    )
    results["workspace_explore_read"] = dur
    print(f"6b. workspace_explore(action='read'): {dur:.2f} ms [ok: {res.get('ok')}, lines: {res.get('total_lines')}]")

    # 7. terminal_execute
    res, dur = time_call(
        terminal_execute,
        command="python3 -c 'print(sum(range(100000)))'",
        cwd=str(ws_path),
        chat_id=chat_id,
    )
    results["terminal_execute"] = dur
    print(f"7. terminal_execute: {dur:.2f} ms [ok: {res.get('ok')}, exit_code: {res.get('exit_code')}]")

    # 8. task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    res, dur = loop.run_until_complete(time_async_call(task, action="list", chat_id=chat_id))
    results["task_list"] = dur
    print(f"8. task(action='list'): {dur:.2f} ms [ok: {res.get('ok') if isinstance(res, dict) else True}]")

    # =========================================================================
    # 9. DEEP DIVE: workspace_search LATENCY PROFILING
    # =========================================================================
    print("\n----------------------------------------------------------------")
    print("         DEEP DIVE: workspace_search LATENCY PROFILING          ")
    print("----------------------------------------------------------------")

    # Populate a dataset of 50 files with varying sizes and content
    data_dir = ws_path / "search_dataset"
    data_dir.mkdir(parents=True, exist_ok=True)
    for i in range(50):
        lines = [f"# File {i} header"]
        for j in range(100):
            if (i + j) % 7 == 0:
                lines.append(f"TARGET_FLAG_BQA_{i}_{j} = 'CRITICAL_MATCH'")
            else:
                lines.append(f"filler_variable_{j} = {j * 3}")
        (data_dir / f"module_{i:02d}.py").write_text("\n".join(lines), encoding="utf-8")

    # Sub-test A: Ripgrep Content Search
    res, dur_rg_content = time_call(
        workspace_search,
        path=str(data_dir),
        query="CRITICAL_MATCH",
        mode="content",
        max_matches=100,
        chat_id=chat_id,
    )
    print(f"A. Ripgrep Content Search:")
    print(f"   - Total Duration: {dur_rg_content:.2f} ms")
    print(f"   - Engine Duration: {res.get('engine_duration_ms', 0):.2f} ms")
    print(f"   - Matches Returned: {len(res.get('matches', []))}")
    print(f"   - Scanned: {res.get('scanned_files')} files ({res.get('scanned_bytes')} bytes)")
    print(f"   - Engine Used: {res.get('engine')}")

    # Sub-test B: Ripgrep Path Search
    res, dur_rg_path = time_call(
        workspace_search,
        path=str(data_dir),
        query="module_0",
        mode="path",
        max_matches=100,
        chat_id=chat_id,
    )
    print(f"\nB. Ripgrep Path Search:")
    print(f"   - Total Duration: {dur_rg_path:.2f} ms")
    print(f"   - Engine Duration: {res.get('engine_duration_ms', 0):.2f} ms")
    print(f"   - Matches Returned: {len(res.get('matches', []))}")
    print(f"   - Scanned: {res.get('scanned_files')} files")
    print(f"   - Engine Used: {res.get('engine')}")

    # Sub-test C: Ripgrep Regex Search
    res, dur_rg_regex = time_call(
        workspace_search,
        path=str(data_dir),
        query=r"TARGET_FLAG_BQA_\d+_14",
        mode="content",
        regex=True,
        max_matches=100,
        chat_id=chat_id,
    )
    print(f"\nC. Ripgrep Regex Search:")
    print(f"   - Total Duration: {dur_rg_regex:.2f} ms")
    print(f"   - Engine Duration: {res.get('engine_duration_ms', 0):.2f} ms")
    print(f"   - Matches Returned: {len(res.get('matches', []))}")
    print(f"   - Scanned: {res.get('scanned_files')} files")
    print(f"   - Engine Used: {res.get('engine')}")

    # Sub-test D: Python Fallback Search (simulating environments without ripgrep)
    import app.tools.workspace_search as search_mod
    original_which = search_mod.shutil.which
    search_mod.shutil.which = lambda _cmd: None
    try:
        res, dur_py_content = time_call(
            workspace_search,
            path=str(data_dir),
            query="CRITICAL_MATCH",
            mode="content",
            max_matches=100,
            chat_id=chat_id,
        )
        print(f"\nD. Python Fallback Content Search (no rg binary):")
        print(f"   - Total Duration: {dur_py_content:.2f} ms")
        print(f"   - Engine Duration: {res.get('engine_duration_ms', 0):.2f} ms")
        print(f"   - Matches Returned: {len(res.get('matches', []))}")
        print(f"   - Scanned: {res.get('scanned_files')} files ({res.get('scanned_bytes')} bytes)")
        print(f"   - Engine Used: {res.get('engine')}")
    finally:
        search_mod.shutil.which = original_which

    # Save benchmark metrics to json
    benchmark_report = {
        "summary": results,
        "search_profiling": {
            "ripgrep_content_duration_ms": dur_rg_content,
            "ripgrep_path_duration_ms": dur_rg_path,
            "ripgrep_regex_duration_ms": dur_rg_regex,
            "python_fallback_content_duration_ms": dur_py_content,
        },
    }
    out_file = Path("/home/light/Downloads/bqa-trash/benchmark_results.json")
    out_file.write_text(json.dumps(benchmark_report, indent=2))
    print(f"\nBenchmark metrics written to {out_file}")


if __name__ == "__main__":
    main()
