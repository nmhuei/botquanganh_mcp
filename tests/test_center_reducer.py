from app.cli.center.events import (
    ActivityViewportChanged,
    LogsJumpToLatest,
    LogsViewportChanged,
    OperationObserved,
    RuntimeSnapshotFailed,
    RuntimeSnapshotReceived,
    SessionActivityObserved,
    SessionDiscovered,
    SessionSelected,
    UiPreferenceChanged,
    WorkspaceLogObserved,
)
from app.cli.center.models import OperationStatus
from app.cli.center.reducer import reduce_event
from app.cli.center.selectors import visible_logs, visible_operations, visible_sessions
from app.cli.center.state import CenterState


def test_unrelated_activity_never_steals_selected_session():
    state = CenterState()
    reduce_event(state, SessionDiscovered(chat_id="session-1", created_at=1))
    reduce_event(state, SessionDiscovered(chat_id="session-2", created_at=2))
    reduce_event(state, SessionSelected(chat_id="session-1"))

    reduce_event(
        state,
        SessionActivityObserved(
            chat_id="session-2",
            operation_id="op-2",
            observed_at=10,
        ),
    )

    assert state.sessions.selected_id == "session-1"
    assert state.sessions.by_id["session-2"].unread_count == 1
    assert state.sessions.by_id["session-2"].visible is True


def test_first_activity_selects_only_when_nothing_is_selected():
    state = CenterState()

    reduce_event(
        state,
        SessionActivityObserved(
            chat_id="session-1",
            operation_id="op-1",
            observed_at=10,
        ),
    )

    assert state.sessions.selected_id == "session-1"
    assert state.sessions.by_id["session-1"].unread_count == 0


def test_session_order_is_creation_order_not_recent_activity():
    state = CenterState()
    reduce_event(state, SessionDiscovered(chat_id="newer", created_at=20))
    reduce_event(state, SessionDiscovered(chat_id="older", created_at=10))
    reduce_event(
        state,
        SessionActivityObserved(chat_id="older", operation_id="op", observed_at=999),
    )

    assert state.sessions.order == ["older", "newer"]
    assert state.sessions.by_id["older"].last_activity_at == 999


def test_terminal_operation_cannot_regress_to_running():
    state = CenterState()
    reduce_event(
        state,
        OperationObserved(
            event_id="done",
            operation_id="op-1",
            chat_id="chat",
            status="succeeded",
            phase="completed",
            timestamp=2,
        ),
    )
    reduce_event(
        state,
        OperationObserved(
            event_id="late-start",
            operation_id="op-1",
            chat_id="chat",
            status="running",
            phase="started",
            timestamp=1,
        ),
    )

    assert state.operations.by_id["op-1"].status == OperationStatus.SUCCEEDED


def test_operation_transition_updates_session_counters_once():
    state = CenterState()
    reduce_event(
        state,
        OperationObserved(
            event_id="start",
            operation_id="op-1",
            chat_id="chat",
            status="running",
            timestamp=1,
        ),
    )
    assert state.sessions.by_id["chat"].operation_count == 1
    assert state.sessions.by_id["chat"].running_count == 1

    reduce_event(
        state,
        OperationObserved(
            event_id="done",
            operation_id="op-1",
            chat_id="chat",
            status="failed",
            timestamp=2,
        ),
    )
    session = state.sessions.by_id["chat"]
    assert session.operation_count == 1
    assert session.running_count == 0
    assert session.failed_count == 1


def test_runtime_failure_keeps_last_good_snapshot_and_marks_stale():
    state = CenterState()
    reduce_event(
        state,
        RuntimeSnapshotReceived(
            data={
                "bridge": "ready",
                "server": {"running": True, "pid": 10},
                "tunnel": {"running": True, "pid": 20},
                "connector_ready": True,
                "url": "https://example/mcp",
                "workspace": "/tmp",
            },
            observed_at=10,
        ),
    )

    reduce_event(
        state,
        RuntimeSnapshotFailed(error="timeout", observed_at=20),
    )

    assert state.runtime.snapshot.server_pid == 10
    assert state.runtime.snapshot.tunnel_pid == 20
    assert state.runtime.snapshot.connector_url == "https://example/mcp"
    assert state.runtime.snapshot.stale is True
    assert state.runtime.last_error == "timeout"


def test_logs_pause_auto_follow_and_count_unseen():
    state = CenterState()
    reduce_event(state, LogsViewportChanged(at_bottom=False))
    for index in range(3):
        reduce_event(
            state,
            WorkspaceLogObserved(
                event_id=f"log-{index}",
                payload={
                    "event_id": f"log-{index}",
                    "event_action": "host_run_command",
                    "event_outcome": "success",
                },
            ),
        )

    assert state.logs.unseen_count == 3
    reduce_event(state, LogsJumpToLatest())
    assert state.logs.unseen_count == 0
    assert state.logs.at_bottom is True


def test_activity_pause_auto_follow_and_count_unseen():
    state = CenterState()
    reduce_event(state, ActivityViewportChanged(at_bottom=False))
    reduce_event(
        state,
        OperationObserved(
            event_id="start",
            operation_id="op-1",
            chat_id="chat",
            status="running",
            timestamp=1,
        ),
    )
    assert state.ui.activity_unseen_count == 1


def test_ui_preference_change_never_mutates_runtime():
    state = CenterState()
    original = state.runtime.snapshot
    reduce_event(state, UiPreferenceChanged(key="language", value="vi"))
    assert state.ui.language == "vi"
    assert state.runtime.snapshot == original


def test_selectors_return_creation_order_newest_operations_and_filtered_logs():
    state = CenterState()
    reduce_event(state, SessionDiscovered(chat_id="a", created_at=1))
    reduce_event(state, SessionDiscovered(chat_id="b", created_at=2))
    reduce_event(state, SessionActivityObserved(chat_id="a", observed_at=3))
    reduce_event(state, SessionActivityObserved(chat_id="b", observed_at=4))
    assert [row.chat_id for row in visible_sessions(state)] == ["a", "b"]

    reduce_event(
        state,
        OperationObserved(
            operation_id="op-a",
            chat_id="a",
            status="running",
            command="python alpha.py",
            timestamp=1,
        ),
    )
    reduce_event(
        state,
        OperationObserved(
            operation_id="op-b",
            chat_id="b",
            status="running",
            command="python beta.py",
            timestamp=2,
        ),
    )
    reduce_event(state, SessionSelected(chat_id="b"))
    assert [row.operation_id for row in visible_operations(state)] == ["op-b"]

    reduce_event(
        state,
        WorkspaceLogObserved(
            event_id="e1",
            payload={
                "event_id": "e1",
                "chat_id": "a",
                "severity_text": "INFO",
                "event_outcome": "success",
                "event_category": "file",
            },
        ),
    )
    reduce_event(
        state,
        WorkspaceLogObserved(
            event_id="e2",
            payload={
                "event_id": "e2",
                "chat_id": "b",
                "severity_text": "ERROR",
                "event_outcome": "failure",
                "event_category": "process",
            },
        ),
    )
    state.logs.outcome_filter = "failure"
    assert [row.event_id for row in visible_logs(state)] == ["e2"]
