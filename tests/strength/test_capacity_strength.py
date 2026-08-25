import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.error_contract import ServiceBusyError
from app.host.executor import CommandCapacity


def test_capacity_storm_preserves_invariants():
    capacity = CommandCapacity(max_concurrent=16, queue_timeout_seconds=0.15)
    rng = random.Random(20260825)
    attempts = 240
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            capacity.acquire()
        except ServiceBusyError:
            with lock:
                outcomes.append("busy")
            return
        with lock:
            outcomes.append("started")
        time.sleep(rng.uniform(0.001, 0.01))
        capacity.release()

    with ThreadPoolExecutor(max_workers=48) as pool:
        futures = [pool.submit(worker, index) for index in range(attempts)]
        for future in futures:
            future.result(timeout=30)

    stats = capacity.get_stats()
    assert len(outcomes) == attempts
    assert outcomes.count("started") == stats["started"]
    assert outcomes.count("busy") == stats["rejected"]
    assert stats["started"] + stats["rejected"] == attempts
    assert stats["peak_active"] <= 16
    assert stats["peak_active"] >= 2
    assert stats["active"] == 0
    assert stats["queued"] == 0


def test_queued_caller_is_admitted_when_slot_frees_before_timeout():
    capacity = CommandCapacity(max_concurrent=1, queue_timeout_seconds=5)
    hold = threading.Event()
    admitted_second = threading.Event()
    capacity.acquire()

    def queued_worker() -> None:
        capacity.acquire()
        admitted_second.set()
        capacity.release()

    thread = threading.Thread(target=queued_worker)
    thread.start()
    time.sleep(0.05)
    assert not admitted_second.is_set()
    assert capacity.get_stats()["queued"] == 1
    hold.set()
    capacity.release()
    assert admitted_second.wait(timeout=2)
    thread.join(timeout=2)
    capacity.release()
    stats = capacity.get_stats()
    assert stats["active"] == 0
    assert stats["started"] == 2
    assert stats["rejected"] == 0


def test_double_release_does_not_grant_extra_slots():
    capacity = CommandCapacity(max_concurrent=1, queue_timeout_seconds=0.3)
    capacity.acquire()
    capacity.release()
    capacity.release()

    hold = threading.Event()
    holder_entered = threading.Event()
    second_outcome: list[str] = []

    def holder() -> None:
        try:
            capacity.acquire()
        except ServiceBusyError:
            return
        holder_entered.set()
        hold.wait(timeout=5)
        capacity.release()

    def second() -> None:
        try:
            capacity.acquire()
            capacity.release()
            second_outcome.append("admitted")
        except ServiceBusyError:
            second_outcome.append("busy")

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert holder_entered.wait(timeout=2)

    second_thread = threading.Thread(target=second)
    second_thread.start()
    second_thread.join(timeout=5)

    assert second_outcome == ["busy"], (
        "phantom slot granted after spurious double release"
    )
    hold.set()
    holder_thread.join(timeout=5)
    stats = capacity.get_stats()
    assert stats["active"] == 0
    assert stats["peak_active"] == 1


def test_release_on_never_acquired_capacity_is_harmless():
    capacity = CommandCapacity(max_concurrent=3, queue_timeout_seconds=0.05)
    capacity.release()
    capacity.release()
    stats = capacity.get_stats()
    assert stats["active"] == 0


def test_repeated_random_interleavings_keep_accounting_consistent():
    for seed in range(5):
        rng = random.Random(seed)
        capacity = CommandCapacity(max_concurrent=4, queue_timeout_seconds=0.02)
        acquired_count = 0
        lock = threading.Lock()

        def worker(index: int) -> None:
            nonlocal acquired_count
            if rng.random() < 0.5:
                time.sleep(rng.uniform(0, 0.002))
            try:
                capacity.acquire()
            except ServiceBusyError:
                return
            with lock:
                acquired_count += 1
            time.sleep(rng.uniform(0, 0.003))
            capacity.release()

        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(worker, index) for index in range(120)]
            for future in futures:
                future.result(timeout=30)

        stats = capacity.get_stats()
        assert stats["active"] == 0
        assert stats["queued"] == 0
        assert stats["started"] == acquired_count
        assert stats["peak_active"] <= 4
