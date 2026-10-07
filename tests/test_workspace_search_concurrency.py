"""Concurrency and outcome contract (Task 2, RED)."""

from __future__ import annotations

import pytest


def test_capacity_rejects_second_chat_search_before_engine():
    from app.search_runtime import SearchCapacity
    from app.error_contract import ServiceBusyError

    manager = SearchCapacity(global_limit=1, per_chat_limit=1, queue_timeout=0)
    first = manager.acquire("chat-a")
    try:
        with pytest.raises(ServiceBusyError):
            manager.acquire("chat-b")
    finally:
        first.release()


def test_partial_outcome_marks_deadline_without_error():
    from app.search_models import SearchLimitReason, SearchOutcome

    outcome = SearchOutcome.partial(SearchLimitReason.DEADLINE)
    assert outcome.ok is True
    assert outcome.count_complete is False
    assert outcome.limit_reason is SearchLimitReason.DEADLINE
    assert outcome.error is None


def test_per_chat_limit_is_independent():
    from app.search_runtime import SearchCapacity

    manager = SearchCapacity(global_limit=10, per_chat_limit=1, queue_timeout=0)
    first = manager.acquire("chat-a")
    try:
        second = manager.acquire("chat-b")
        second.release()
    finally:
        first.release()


def test_lease_release_is_idempotent():
    from app.search_runtime import SearchCapacity

    manager = SearchCapacity(global_limit=1, per_chat_limit=1, queue_timeout=5)
    lease = manager.acquire("chat-a")
    lease.release()
    lease.release()
    # Capacity is free again after idempotent release.
    again = manager.acquire("chat-a")
    again.release()
