"""Strength probes for the dedicated REST blocking pool.

Regression coverage for moving blocking REST handlers off Starlette's shared
default threadpool onto ``app.rest_api._REST_BLOCKING_POOL``
(an ``anyio.CapacityLimiter(16)`` consumed via ``anyio.to_thread.run_sync``):

1. A burst of slow POST /api/v1/commands/run calls must cap concurrent
   blocking work at exactly 16 while both pool-free routes keep answering
   under a strict deadline: GET /healthz answers straight from the ASGI
   stack, and GET /api/v1/health dispatches its handler inline via
   ``app.rest_api._call_nowait`` (the handler only reads in-memory metrics,
   no I/O), so neither touches any worker pool. Previously /api/v1/health
   went through the same blocking limiter and queued behind the storm.
2. CommandCapacity must still bound the real executor underneath the pool:
   overflow requests surface SERVICE_BUSY once the queue timeout expires and
   the active count drains back to zero afterwards.
"""

from __future__ import annotations

import threading
import time

import pytest

import app.host.executor as executor_module
import app.rest_api
from app.host.executor import CommandCapacity
from app.mcp_server import mcp

pytestmark = pytest.mark.strength

_POOL_FREE_DEADLINE_SECONDS = 0.2
_POOL_FREE_PROBE_PATHS = ("/healthz", "/api/v1/health")


@pytest.fixture()
def rest_client():
    from starlette.testclient import TestClient

    application = mcp.http_app(path="/mcp", transport="streamable-http")
    # One entered client shares a single blocking portal; anyio portals accept
    # concurrent calls from many threads, which is what the storms below rely on.
    with TestClient(application) as client:
        yield client


def test_blocking_pool_saturates_at_16_and_lightweight_routes_stay_live(
    rest_client, monkeypatch
):
    pool_width = 16
    storm_size = 24  # > pool_width so 8 callers must queue behind the limiter
    hold_seconds = 0.6  # long enough for every post to line up in one window

    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def slow_stub(command, *, cwd=None, timeout_seconds=30):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(hold_seconds)
        with lock:
            in_flight -= 1
        return {"ok": True}

    # api_run_command resolves execute_host_command from rest_api's module
    # globals at call time, so patching that namespace swaps the seam without
    # spawning a single process.
    monkeypatch.setattr(app.rest_api, "execute_host_command", slow_stub)

    barrier = threading.Barrier(storm_size + 1)
    statuses: list[int | None] = [None] * storm_size
    failures: list[BaseException] = []

    def poster(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            response = rest_client.post(
                "/api/v1/commands/run",
                json={"command": "pool-storm-noop", "timeout_seconds": 5},
            )
            statuses[index] = response.status_code
        except BaseException as exc:  # recorded here, asserted below
            failures.append(exc)

    threads = [
        threading.Thread(target=poster, args=(index,), name=f"pool-storm-{index}")
        for index in range(storm_size)
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=15)

    drain_deadline = time.monotonic() + 20.0
    probes = 0
    while any(thread.is_alive() for thread in threads):
        assert time.monotonic() < drain_deadline, "command storm did not drain"
        for path in _POOL_FREE_PROBE_PATHS:
            started = time.monotonic()
            response = rest_client.get(path)
            elapsed = time.monotonic() - started
            assert response.status_code == 200, response.text
            assert elapsed < _POOL_FREE_DEADLINE_SECONDS, (
                f"{path} answered in {elapsed * 1000:.0f}ms while the blocking "
                f"pool was saturated"
            )
        probes += 1
        time.sleep(0.05)

    for thread in threads:
        thread.join(timeout=5)

    assert not failures, failures
    assert probes >= 3, f"expected repeated probes during saturation, made {probes}"
    assert all(status == 200 for status in statuses), statuses
    assert peak <= pool_width, (
        f"{peak} blocking handlers ran concurrently, above the {pool_width}-slot pool"
    )
    assert peak == pool_width, (
        f"blocking pool never saturated: peaked at {peak}/{pool_width}"
    )


def test_capacity_gate_still_bounds_real_executions(
    rest_client, isolated_workspace, monkeypatch
):
    limit = 2
    overflow = 4
    capacity = CommandCapacity(max_concurrent=limit, queue_timeout_seconds=0.05)
    monkeypatch.setattr(executor_module, "command_capacity", capacity)

    total = limit + overflow
    barrier = threading.Barrier(total + 1)
    outcomes: list[tuple[int, dict]] = []
    failures: list[BaseException] = []
    outcomes_lock = threading.Lock()

    def runner() -> None:
        try:
            barrier.wait(timeout=15)
            response = rest_client.post(
                "/api/v1/commands/run",
                json={"command": "sleep 0.4", "timeout_seconds": 5},
            )
            outcome = (response.status_code, response.json())
        except BaseException as exc:  # recorded here, asserted below
            failures.append(exc)
            return
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=runner, name=f"capacity-run-{index}")
        for index in range(total)
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=15)
    for thread in threads:
        thread.join(timeout=15)
    assert not any(thread.is_alive() for thread in threads), "runner hung"

    assert not failures, failures
    assert len(outcomes) == total, f"missing outcomes: {outcomes}"

    admitted = [body for status, body in outcomes if status == 200]
    rejected = [body for status, body in outcomes if status != 200]
    assert len(admitted) == limit, outcomes
    assert all(body.get("ok") is True for body in admitted), admitted
    assert len(rejected) == overflow, outcomes
    for body in rejected:
        assert body["error"]["code"] == "SERVICE_BUSY", body

    stats = capacity.get_stats()
    assert stats["active"] == 0, stats
    assert stats["queued"] == 0, stats
    assert stats["rejected"] == overflow, stats
    assert stats["peak_active"] == limit, stats
