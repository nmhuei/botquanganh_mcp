#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 15,
) -> tuple[int, dict[str, Any], float]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                response.status,
                json.load(response),
                (time.perf_counter() - started) * 1000,
            )
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc), (time.perf_counter() - started) * 1000


def benchmark_health(base_url: str, count: int, workers: int) -> dict[str, Any]:
    def one(_index: int) -> float:
        status, body, latency = request_json(
            base_url.rstrip("/") + "/api/v1/health",
            timeout=15,
        )
        if status != 200 or body.get("ok") is not True:
            raise RuntimeError(f"health request failed: HTTP {status}: {body}")
        return latency

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        values = list(pool.map(one, range(count)))
    total_ms = (time.perf_counter() - started) * 1000
    values.sort()
    return {
        "count": len(values),
        "workers": workers,
        "total_ms": round(total_ms, 1),
        "requests_per_second": round(count / max(total_ms / 1000, 0.001), 1),
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(values[max(0, int(len(values) * 0.95) - 1)], 1),
        "max_ms": round(max(values), 1),
    }


def benchmark_command_capacity(
    base_url: str,
    requests: int,
    workers: int,
    sleep_seconds: float,
) -> dict[str, Any]:
    payload = {
        "command": (
            "python3 -c \"import time; "
            f"time.sleep({sleep_seconds!r}); print('done')\""
        ),
        "cwd": "botquanganh_mcp",
        "timeout_seconds": max(5, int(sleep_seconds) + 5),
    }

    def one(_index: int) -> tuple[int, dict[str, Any], float]:
        return request_json(
            base_url.rstrip("/") + "/api/v1/commands/run",
            payload=payload,
            timeout=max(15, sleep_seconds + 10),
        )

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, range(requests)))
    total_ms = (time.perf_counter() - started) * 1000
    statuses = [status for status, _body, _latency in results]
    service_busy = [
        body
        for status, body, _latency in results
        if status == 503
    ]
    if any(body.get("error", {}).get("code") != "SERVICE_BUSY" for body in service_busy):
        raise RuntimeError("503 response did not use SERVICE_BUSY contract")
    return {
        "requests": requests,
        "workers": workers,
        "sleep_seconds": sleep_seconds,
        "total_ms": round(total_ms, 1),
        "status_counts": {
            str(status): statuses.count(status) for status in sorted(set(statuses))
        },
        "latencies_ms": [round(latency, 1) for _status, _body, latency in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive resilience benchmark")
    parser.add_argument("--local-base", default="http://127.0.0.1:8000")
    parser.add_argument("--public-base")
    parser.add_argument("--health-count", type=int, default=40)
    parser.add_argument("--health-workers", type=int, default=10)
    parser.add_argument("--command-requests", type=int, default=8)
    parser.add_argument("--command-workers", type=int, default=8)
    parser.add_argument("--command-sleep", type=float, default=3.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "generated_at_epoch": time.time(),
        "command_capacity": benchmark_command_capacity(
            args.local_base,
            args.command_requests,
            args.command_workers,
            args.command_sleep,
        ),
        "local_health": benchmark_health(
            args.local_base,
            args.health_count,
            args.health_workers,
        ),
    }
    if args.public_base:
        report["public_health"] = benchmark_health(
            args.public_base,
            args.health_count,
            args.health_workers,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
