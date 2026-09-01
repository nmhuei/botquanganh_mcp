#!/usr/bin/env python3
"""Repeatable micro-benchmark for BQA Center QML list-model update paths."""

from __future__ import annotations

import argparse
import json
import statistics
import time

from app.qml_ui.models import OperationListModel


def rows(count: int, *, offset: int = 0, status: str = "succeeded"):
    return [
        {
            "operationId": f"bench-op-{offset + index}",
            "utc": "2026-08-30 00:00:00.000Z",
            "status": status,
            "command": f"python solve.py --case {offset + index}",
            "exit": "0",
            "duration": "12",
            "chatId": f"cw-bench-{(offset + index) % 48:02d}",
            "cwd": "/tmp/benchmark",
            "stdout": "",
            "stderr": "",
            "metadata": "{}",
            "human": "",
        }
        for index in range(count)
    ]


def measure(callable_, repetitions: int) -> list[float]:
    samples = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        callable_()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return samples


def summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()

    model = OperationListModel()
    base = rows(args.rows)

    initial = measure(lambda: model.sync(base), 1)

    changed = [dict(row) for row in base]
    for index in range(0, min(len(changed), 100), 5):
        changed[index]["status"] = "failed"
    toggle = {"changed": False}

    def update_stable_keys() -> None:
        toggle["changed"] = not toggle["changed"]
        model.sync(changed if toggle["changed"] else base)

    updates = measure(update_stable_keys, args.repetitions)

    model.sync(changed)
    prepended = rows(10, offset=args.rows, status="running") + changed
    prepend = measure(lambda: model.sync(prepended), 1)

    result = {
        "rows": args.rows,
        "repetitions": args.repetitions,
        "initial_sync": summary(initial),
        "stable_key_update": summary(updates),
        "prepend_10": summary(prepend),
        "final_rows": model.rowCount(),
        "note": "Measurement only; no flaky timing threshold is enforced.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
