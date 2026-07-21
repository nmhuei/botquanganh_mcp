import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.config
import app.host.executor as executor
import app.ratelimit as ratelimit
from app.error_contract import ServiceBusyError, format_exception_error, http_status_for_exception
from app.host.executor import CommandCapacity
from app.tools.health import get_capabilities, health_check


def test_command_capacity_bounds_active_and_rejects_queue_timeout():
    capacity = CommandCapacity(max_concurrent=2, queue_timeout_seconds=0.05)
    release = threading.Event()
    entered = []

    def worker(index: int) -> str:
        try:
            capacity.acquire()
        except ServiceBusyError:
            return "busy"
        entered.append(index)
        release.wait(timeout=2)
        capacity.release()
        return "started"

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, index) for index in range(8)]
        deadline = time.monotonic() + 1
        while len(entered) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(entered) == 2
        time.sleep(0.08)
        release.set()
        results = [future.result(timeout=2) for future in futures]

    assert results.count("started") == 2
    assert results.count("busy") == 6
    stats = capacity.get_stats()
    assert stats["peak_active"] == 2
    assert stats["active"] == 0
    assert stats["queued"] == 0
    assert stats["rejected"] == 6


def test_executor_returns_service_busy_when_capacity_is_full(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    monkeypatch.setattr(app.config, "HOST_COMMAND_POLICY", "guarded")
    capacity = CommandCapacity(max_concurrent=1, queue_timeout_seconds=0.01)
    capacity.acquire()
    monkeypatch.setattr(executor, "command_capacity", capacity)
    try:
        with pytest.raises(ServiceBusyError):
            executor.execute_host_command("printf blocked", timeout_seconds=2)
    finally:
        capacity.release()

    body = format_exception_error(ServiceBusyError("full"))
    assert body["error"]["code"] == "SERVICE_BUSY"
    assert http_status_for_exception(ServiceBusyError("full")) == 503


def test_command_capacity_releases_after_validation_error(tmp_path, monkeypatch):
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    capacity = CommandCapacity(max_concurrent=1, queue_timeout_seconds=0)
    monkeypatch.setattr(executor, "command_capacity", capacity)

    with pytest.raises(ValueError):
        executor.execute_host_command("printf x", timeout_seconds=0)
    assert capacity.get_stats()["active"] == 0


def test_rate_limiter_bounds_client_state_conservatively(monkeypatch):
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", True)
    limiter = ratelimit.SlidingWindowRateLimiter()
    limiter.max_clients = 3
    limiter.max_requests = 10
    limiter.window_seconds = 60

    assert limiter.is_allowed("one")[0] is True
    assert limiter.is_allowed("two")[0] is True
    assert limiter.is_allowed("three")[0] is True
    allowed, retry_after = limiter.is_allowed("four")
    assert allowed is False
    assert retry_after >= 1

    stats = limiter.get_stats()
    assert stats["tracked_clients"] == 3
    assert stats["capacity_rejected"] == 1
    # Existing clients keep their active quotas rather than being silently evicted.
    assert limiter.is_allowed("one")[0] is True


def test_rate_limiter_prunes_stale_clients_before_capacity_rejection(monkeypatch):
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", True)
    clock = iter([0.0, 0.1, 2.0])
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: next(clock))
    limiter = ratelimit.SlidingWindowRateLimiter()
    limiter.max_clients = 2
    limiter.max_requests = 10
    limiter.window_seconds = 1

    assert limiter.is_allowed("old-one")[0] is True
    assert limiter.is_allowed("old-two")[0] is True
    assert limiter.is_allowed("new-client")[0] is True
    stats = limiter.get_stats()
    assert stats["tracked_clients"] == 1
    assert stats["pruned_clients"] == 2


def test_health_and_capabilities_expose_capacity():
    health = health_check()
    assert "capacity" in health
    assert "commands" in health["capacity"]
    assert "rate_limiter" in health["capacity"]
    capabilities = get_capabilities()
    assert capabilities["limits"]["max_concurrent_commands"] >= 1
    assert capabilities["limits"]["rate_limit_max_clients"] >= 1
