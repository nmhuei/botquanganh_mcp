#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx


MCP_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


@dataclass(slots=True)
class PhaseResult:
    name: str
    count: int = 0
    concurrency: int = 0
    duration_s: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    statuses: Counter[int] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        duration = max(self.duration_s, 1e-9)
        return {
            "name": self.name,
            "count": self.count,
            "concurrency": self.concurrency,
            "duration_s": round(self.duration_s, 3),
            "requests_per_second": round(self.count / duration, 1),
            "status_counts": {str(k): v for k, v in sorted(self.statuses.items())},
            "errors": self.errors[:20],
            "error_count": len(self.errors),
            "latency_ms": {
                "p50": round(percentile(self.latencies_ms, 0.50), 2),
                "p95": round(percentile(self.latencies_ms, 0.95), 2),
                "p99": round(percentile(self.latencies_ms, 0.99), 2),
                "max": round(max(self.latencies_ms), 2) if self.latencies_ms else 0.0,
            },
            "metadata": self.metadata,
        }


def proc_snapshot(pid: int | None) -> dict[str, Any] | None:
    if not pid:
        return None
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return {"alive": False, "pid": pid}
    status: dict[str, str] = {}
    try:
        for line in (proc / "status").read_text(encoding="utf-8").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                status[key] = value.strip()
        stat_parts = (proc / "stat").read_text(encoding="utf-8").split()
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        cpu_seconds = (int(stat_parts[13]) + int(stat_parts[14])) / ticks
        fd_count = len(list((proc / "fd").iterdir()))
        task_dirs = list((proc / "task").iterdir())
        thread_count = len(task_dirs)
        thread_names: dict[str, int] = {}
        for task_dir in task_dirs:
            try:
                name = (task_dir / "comm").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            thread_names[name] = thread_names.get(name, 0) + 1
    except (OSError, ValueError, IndexError):
        return {"alive": proc.exists(), "pid": pid, "read_error": True}

    def kb_value(name: str) -> int:
        raw = status.get(name, "0 kB").split()[0]
        try:
            return int(raw)
        except ValueError:
            return 0

    return {
        "alive": True,
        "pid": pid,
        "rss_kb": kb_value("VmRSS"),
        "rss_mb": round(kb_value("VmRSS") / 1024, 2),
        "peak_rss_mb": round(kb_value("VmHWM") / 1024, 2),
        "fd_count": fd_count,
        "thread_count": thread_count,
        "thread_names": thread_names,
        "anyio_worker_threads": sum(
            count for name, count in thread_names.items() if name.startswith("AnyIO worker")
        ),
        "cpu_seconds": round(cpu_seconds, 3),
    }


async def resource_sampler(pid: int, stop: asyncio.Event, samples: list[dict[str, Any]]) -> None:
    while not stop.is_set():
        snapshot = proc_snapshot(pid)
        if snapshot:
            samples.append(snapshot)
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.1)
        except asyncio.TimeoutError:
            pass


async def run_fixed_phase(
    name: str,
    count: int,
    concurrency: int,
    operation: Callable[[httpx.AsyncClient, int], Awaitable[tuple[int, dict[str, Any] | None]]],
    client: httpx.AsyncClient,
) -> PhaseResult:
    result = PhaseResult(name=name, count=count, concurrency=concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(index: int) -> None:
        async with semaphore:
            started = time.perf_counter()
            try:
                status, payload = await operation(client, index)
                result.statuses[status] += 1
                if status != 200:
                    result.errors.append(f"request {index}: HTTP {status}: {payload!r}")
            except Exception as exc:  # noqa: BLE001 - benchmark must collect all failures
                result.errors.append(f"request {index}: {type(exc).__name__}: {exc}")
            finally:
                result.latencies_ms.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one(index) for index in range(count)))
    result.duration_s = time.perf_counter() - started
    return result


async def op_health(client: httpx.AsyncClient, _index: int) -> tuple[int, dict[str, Any] | None]:
    response = await client.get("/api/v1/health")
    payload = response.json()
    if response.status_code == 200 and payload.get("ok") is not True:
        raise RuntimeError(f"health ok=false: {payload}")
    return response.status_code, payload


async def op_initialize(client: httpx.AsyncClient, index: int) -> tuple[int, dict[str, Any] | None]:
    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "bqa-stress", "version": "1.0"},
            },
        },
    )
    payload = response.json()
    if response.status_code == 200 and "result" not in payload:
        raise RuntimeError(f"initialize missing result: {payload}")
    return response.status_code, payload


async def op_tools_list(client: httpx.AsyncClient, index: int) -> tuple[int, dict[str, Any] | None]:
    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": index + 1, "method": "tools/list", "params": {}},
    )
    payload = response.json()
    if response.status_code == 200:
        tools = payload.get("result", {}).get("tools")
        if not isinstance(tools, list):
            raise RuntimeError(f"tools/list malformed: {payload}")
    return response.status_code, payload


async def op_tool_health(client: httpx.AsyncClient, index: int) -> tuple[int, dict[str, Any] | None]:
    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": index + 1,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}},
        },
    )
    payload = response.json()
    if response.status_code == 200:
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("isError") is True:
            raise RuntimeError(f"health_check tool failed: {payload}")
    return response.status_code, payload


async def op_command(client: httpx.AsyncClient, index: int) -> tuple[int, dict[str, Any] | None]:
    response = await client.post(
        "/api/v1/commands/run",
        json={
            "command": f"python3 -c \"import time; time.sleep(0.05); print('stress-{index}')\"",
            "timeout_seconds": 5,
        },
    )
    payload = response.json()
    if response.status_code == 200 and payload.get("exit_code") != 0:
        raise RuntimeError(f"command exit != 0: {payload}")
    return response.status_code, payload


async def catalog_fingerprint(client: httpx.AsyncClient) -> tuple[str, int]:
    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    response.raise_for_status()
    tools = response.json().get("result", {}).get("tools", [])
    normalized = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest(), len(tools)


async def run_soak(
    client: httpx.AsyncClient,
    seconds: float,
    concurrency: int,
) -> PhaseResult:
    result = PhaseResult(name="mixed_soak", concurrency=concurrency)
    deadline = time.monotonic() + seconds
    counter = 0
    counter_lock = asyncio.Lock()

    async def worker(worker_id: int) -> None:
        nonlocal counter
        local_index = worker_id * 1_000_000
        operations = (op_health, op_tools_list, op_tool_health)
        while time.monotonic() < deadline:
            operation = operations[local_index % len(operations)]
            started = time.perf_counter()
            try:
                status, payload = await operation(client, local_index)
                result.statuses[status] += 1
                if status != 200:
                    result.errors.append(f"worker {worker_id}: HTTP {status}: {payload!r}")
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"worker {worker_id}: {type(exc).__name__}: {exc}")
            finally:
                result.latencies_ms.append((time.perf_counter() - started) * 1000)
                async with counter_lock:
                    counter += 1
            local_index += 1

    started = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(concurrency)))
    result.duration_s = time.perf_counter() - started
    result.count = counter
    result.metadata["target_seconds"] = seconds
    return result


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    limits = httpx.Limits(
        max_connections=max(100, args.max_concurrency * 2),
        max_keepalive_connections=max(50, args.max_concurrency),
    )
    timeout = httpx.Timeout(args.timeout)
    phases: list[PhaseResult] = []
    resource_samples: list[dict[str, Any]] = []
    stop_sampler = asyncio.Event()
    sampler_task: asyncio.Task[None] | None = None

    before = proc_snapshot(args.pid)
    if args.pid:
        sampler_task = asyncio.create_task(resource_sampler(args.pid, stop_sampler, resource_samples))

    async with httpx.AsyncClient(base_url=args.base.rstrip("/"), timeout=timeout, limits=limits) as client:
        # Warm up the app, HTTP connection pool, tool catalog and Python imports.
        for operation in (op_health, op_initialize, op_tools_list, op_tool_health):
            status, _payload = await operation(client, 0)
            if status != 200:
                raise RuntimeError(f"warmup failed with HTTP {status}")

        catalog_before, tool_count_before = await catalog_fingerprint(client)

        phases.append(await run_fixed_phase("health_sequential", args.health_seq, 1, op_health, client))
        phases.append(
            await run_fixed_phase(
                "health_burst",
                args.health_burst,
                args.health_concurrency,
                op_health,
                client,
            )
        )
        phases.append(
            await run_fixed_phase(
                "mcp_initialize",
                args.mcp_initialize,
                args.mcp_concurrency,
                op_initialize,
                client,
            )
        )
        phases.append(
            await run_fixed_phase(
                "mcp_tools_list",
                args.mcp_list,
                args.mcp_concurrency,
                op_tools_list,
                client,
            )
        )
        phases.append(
            await run_fixed_phase(
                "mcp_health_tool",
                args.mcp_calls,
                args.mcp_call_concurrency,
                op_tool_health,
                client,
            )
        )
        phases.append(await run_soak(client, args.soak_seconds, args.soak_concurrency))
        phases.append(
            await run_fixed_phase(
                "command_execution",
                args.command_count,
                args.command_concurrency,
                op_command,
                client,
            )
        )

        await asyncio.sleep(args.idle_after)
        catalog_after, tool_count_after = await catalog_fingerprint(client)
        final_health = (await client.get("/api/v1/health")).json()

    # Let HTTP keep-alive sockets close after the client itself is gone. This avoids
    # treating transient connection-pool FDs as a server-side leak.
    await asyncio.sleep(args.settle_after)

    if sampler_task:
        stop_sampler.set()
        await sampler_task

    after = proc_snapshot(args.pid)
    phase_dicts = [phase.as_dict() for phase in phases]
    total_errors = sum(item["error_count"] for item in phase_dicts)
    status_5xx = sum(
        count
        for phase in phase_dicts
        for status, count in phase["status_counts"].items()
        if int(status) >= 500
    )

    peak_resources: dict[str, Any] | None = None
    if resource_samples:
        peak_resources = {
            "rss_mb": round(max(float(item.get("rss_mb", 0)) for item in resource_samples), 2),
            "fd_count": max(int(item.get("fd_count", 0)) for item in resource_samples),
            "thread_count": max(int(item.get("thread_count", 0)) for item in resource_samples),
            "samples": len(resource_samples),
        }

    rss_growth_mb = None
    fd_growth = None
    thread_growth = None
    if before and after and before.get("alive") and after.get("alive"):
        rss_growth_mb = round(float(after.get("rss_mb", 0)) - float(before.get("rss_mb", 0)), 2)
        fd_growth = int(after.get("fd_count", 0)) - int(before.get("fd_count", 0))
        thread_growth = int(after.get("thread_count", 0)) - int(before.get("thread_count", 0))

    thread_pool_reasonable = True
    if after and after.get("alive"):
        # FastMCP/Starlette run synchronous tools through AnyIO's worker pool. Those
        # threads are intentionally retained and may grow under the first large
        # burst; they are not a leak. Flag unexpected thread growth or a runaway
        # worker pool, while accepting the normal AnyIO pool size.
        anyio_workers = int(after.get("anyio_worker_threads", 0))
        other_threads = int(after.get("thread_count", 0)) - anyio_workers
        before_anyio = int((before or {}).get("anyio_worker_threads", 0))
        before_other = int((before or {}).get("thread_count", 0)) - before_anyio
        thread_pool_reasonable = anyio_workers <= 40 and other_threads <= before_other + 2

    checks = {
        "zero_request_errors": total_errors == 0,
        "zero_5xx": status_5xx == 0,
        "process_alive": bool(after and after.get("alive")) if args.pid else True,
        "pid_unchanged": bool(before and after and before.get("pid") == after.get("pid")) if args.pid else True,
        "catalog_stable": catalog_before == catalog_after and tool_count_before == tool_count_after,
        "final_health_ok": final_health.get("ok") is True,
        # Generous leak guards: these flag obvious runaway growth while allowing allocator/cache retention.
        "fd_growth_reasonable": fd_growth is None or fd_growth <= 12,
        "thread_pool_reasonable": thread_pool_reasonable,
        "rss_growth_reasonable": rss_growth_mb is None or rss_growth_mb <= 64,
    }

    return {
        "generated_at_epoch": time.time(),
        "base": args.base,
        "pid": args.pid,
        "profile": "isolated-local-stress",
        "phases": phase_dicts,
        "catalog": {
            "before_sha256": catalog_before,
            "after_sha256": catalog_after,
            "tool_count_before": tool_count_before,
            "tool_count_after": tool_count_after,
        },
        "resources": {
            "before": before,
            "after": after,
            "peak": peak_resources,
            "rss_growth_mb": rss_growth_mb,
            "fd_growth": fd_growth,
            "thread_growth": thread_growth,
        },
        "final_health": final_health,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stress and soak a BotQuangAnh MCP endpoint")
    parser.add_argument("--base", required=True, help="Base URL, e.g. http://127.0.0.1:19000")
    parser.add_argument("--pid", type=int, help="Server PID for resource/leak monitoring")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-concurrency", type=int, default=64)
    parser.add_argument("--health-seq", type=int, default=300)
    parser.add_argument("--health-burst", type=int, default=1200)
    parser.add_argument("--health-concurrency", type=int, default=40)
    parser.add_argument("--mcp-initialize", type=int, default=250)
    parser.add_argument("--mcp-list", type=int, default=300)
    parser.add_argument("--mcp-calls", type=int, default=600)
    parser.add_argument("--mcp-concurrency", type=int, default=25)
    parser.add_argument("--mcp-call-concurrency", type=int, default=40)
    parser.add_argument("--soak-seconds", type=float, default=10.0)
    parser.add_argument("--soak-concurrency", type=int, default=30)
    parser.add_argument("--command-count", type=int, default=24)
    parser.add_argument("--command-concurrency", type=int, default=12)
    parser.add_argument("--idle-after", type=float, default=1.0)
    parser.add_argument(
        "--settle-after",
        type=float,
        default=3.0,
        help="Seconds to wait after closing the HTTP client before leak checks",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = asyncio.run(main_async(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
