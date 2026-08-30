from app.cli.center.events import (
    OperationObserved,
    RuntimeSnapshotReceived,
    SessionActivityObserved,
)
from app.cli.center.inbox import BoundedEventInbox


def test_inbox_deduplicates_event_ids():
    duplicates = []
    inbox = BoundedEventInbox(maxsize=4, on_duplicate=lambda: duplicates.append(1))
    event = SessionActivityObserved(event_id="same", chat_id="a")
    assert inbox.put(event) is True
    assert inbox.put(event) is False
    assert duplicates == [1]
    assert len(inbox) == 1


def test_inbox_coalesces_running_operation_updates():
    coalesced = []
    inbox = BoundedEventInbox(maxsize=4, on_coalesced=lambda: coalesced.append(1))
    inbox.put(
        OperationObserved(
            operation_id="op",
            status="running",
            duration_ms=1,
        )
    )
    inbox.put(
        OperationObserved(
            operation_id="op",
            status="running",
            duration_ms=99,
        )
    )

    events = inbox.drain(10)
    assert len(events) == 1
    assert events[0].duration_ms == 99
    assert coalesced == [1]


def test_full_inbox_evicts_low_value_snapshot_before_critical_event():
    dropped = []
    inbox = BoundedEventInbox(maxsize=2, on_dropped=lambda: dropped.append(1))
    inbox.put(RuntimeSnapshotReceived(event_id="r1", data={"n": 1}))
    inbox.put(SessionActivityObserved(event_id="a1", chat_id="a"))
    inbox.put(SessionActivityObserved(event_id="a2", chat_id="b"))

    drained = inbox.drain(10)
    assert [event.event_id for event in drained] == ["a1", "a2"]
    assert dropped == [1]
