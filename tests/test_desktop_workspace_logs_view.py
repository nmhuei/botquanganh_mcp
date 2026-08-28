import threading
import time

from app.cli.desktop_views.workspace_logs import (
    WorkspaceLogRow,
    WorkspaceLogView,
    filter_workspace_log_rows,
    format_workspace_log_details,
    format_workspace_log_time,
    normalize_workspace_log_chip,
    parse_sse_lines,
    workspace_log_inspector_content,
    workspace_log_row_from_mapping,
    workspace_log_row_matches_chip,
)
from app.cli.desktop_views.i18n import DesktopTranslator


def test_workspace_log_view_normalizes_a_journal_event():
    row = workspace_log_row_from_mapping(
        {
            "ts": "2026-08-26T18:00:00+00:00",
            "severity_text": "ERROR",
            "event_category": "process",
            "event_action": "host_run_command",
            "chat_id": "chat-a",
            "event_duration_ms": "12.5",
        },
        event_id="evt-1",
    )

    assert row == WorkspaceLogRow(
        event_id="evt-1",
        timestamp="2026-08-26T18:00:00+00:00",
        severity="ERROR",
        category="process",
        action="host_run_command",
        outcome="unknown",
        phase="",
        chat_id="chat-a",
        duration_ms=12.5,
        interaction_id="",
        dataset="",
        source="",
        payload=None,
    )


def test_workspace_log_view_reports_new_workspace_event_once():
    reopened = []
    view = WorkspaceLogView(on_new_activity=reopened.append)
    envelope = {
        "id": "evt-1",
        "event": "workspace_log",
        "data": {"chat_id": "chat-a", "event_action": "host_run_command"},
    }

    view.accept_event(envelope)
    view.accept_event(envelope)

    assert [(notice.chat_id, notice.operation_id) for notice in reopened] == [
        ("chat-a", "evt-1")
    ]


def test_workspace_log_view_suppresses_initial_replay_and_alerts_once_per_interaction():
    reopened = []
    view = WorkspaceLogView(on_new_activity=reopened.append)
    historic_start = {
        "id": "historic-start",
        "event": "workspace_log",
        "data": {
            "chat_id": "chat-a",
            "interaction_id": "op-historic",
            "operation_phase": "started",
            "event_action": "host_run_command",
        },
    }
    historic_done = {
        "id": "historic-done",
        "event": "workspace_log",
        "data": {
            "chat_id": "chat-a",
            "interaction_id": "op-historic",
            "operation_phase": "result",
            "event_action": "host_run_command",
        },
    }
    live_start = {
        "id": "live-start",
        "event": "workspace_log",
        "data": {
            "chat_id": "chat-b",
            "interaction_id": "op-live",
            "operation_phase": "started",
            "event_action": "host_run_command",
        },
    }
    live_done = {
        "id": "live-done",
        "event": "workspace_log",
        "data": {
            "chat_id": "chat-b",
            "interaction_id": "op-live",
            "operation_phase": "result",
            "event_action": "host_run_command",
        },
    }

    view.accept_control(
        {"event": "stream_replay", "data": {"phase": "start", "baseline": True}}
    )
    view.accept_event(historic_start)
    view.accept_event(historic_done)
    view.accept_control({"event": "stream_replay", "data": {"phase": "complete"}})
    view.accept_event(live_start)
    view.accept_event(live_done)

    assert [(notice.chat_id, notice.operation_id) for notice in reopened] == [
        ("chat-b", "op-live")
    ]


def test_workspace_log_view_close_prevents_future_event_delivery():
    reopened = []
    view = WorkspaceLogView(on_new_activity=reopened.append)
    view.close()
    view.accept_event(
        {"id": "evt-2", "event": "workspace_log", "data": {"chat_id": "chat-a"}}
    )

    assert view.closed is True
    assert view.stop_event.is_set() is True
    assert reopened == []


def test_workspace_log_view_reports_live_and_reset_connection_state():
    states = []
    view = WorkspaceLogView(
        on_new_activity=lambda _chat_id: None,
        on_status_change=lambda state: states.append(state),
    )

    view.accept_event({"id": "evt-1", "event": "workspace_log", "data": {"chat_id": "chat-a"}})
    view.accept_control({"event": "stream_reset", "data": {}})

    assert states == ["live", "reset"]


def test_workspace_log_filters_and_details_remain_copy_safe():
    row = WorkspaceLogRow(
        event_id="evt-2",
        timestamp="2026-08-26T18:01:02+00:00",
        severity="INFO",
        category="file",
        action="host_read_file",
        outcome="success",
        chat_id="chat-beta",
        duration_ms=1.25,
        payload={"path": "repo/README.md"},
    )

    assert workspace_log_row_matches_chip(row, "file") is True
    assert filter_workspace_log_rows([row], chip="all", chat_filter="BETA", outcome="success") == [row]
    assert filter_workspace_log_rows([row], chip="all", outcome="failure") == []
    assert normalize_workspace_log_chip(" ERROR ") == "error"
    assert format_workspace_log_time(row.timestamp) == "2026-08-26 18:01:02"
    assert '"path": "repo/README.md"' in format_workspace_log_details(row)
    inspector = workspace_log_inspector_content(row)
    assert set(inspector) == {"summary", "metadata", "payload"}
    assert '"path": "repo/README.md"' in inspector["payload"]


def test_workspace_logs_language_change_keeps_cached_rows_and_localizes_details():
    row = WorkspaceLogRow(event_id="evt-language", action="host_read_file")
    view = WorkspaceLogView(
        on_new_activity=lambda _chat_id: None,
        translator=DesktopTranslator("en"),
    )
    view.rows = [row]
    view.selected_id = row.event_id

    view.set_translator(DesktopTranslator("vi"))

    assert view.rows == [row]
    assert view.selected_id == "evt-language"
    assert "Thời gian:" in format_workspace_log_details(row, DesktopTranslator("vi"))


def test_workspace_log_view_reset_drops_cursor_cache_and_selection():
    view = WorkspaceLogView(on_new_activity=lambda _chat_id: None)
    view.accept_event({"id": "evt-1", "event": "workspace_log", "data": {"chat_id": "chat-a"}})
    view.selected_id = "evt-1"

    view.accept_control({"event": "stream_reset", "data": {"reason": "cursor_not_found"}})

    assert view.last_event_id is None
    assert view.rows == []
    assert view.selected_id is None
    assert view.connection_status == "reset"


def test_parse_sse_lines_handles_comments_ids_and_multiline_json():
    events = list(
        parse_sse_lines(
            iter(
                [
                    "retry: 2000",
                    "",
                    ": heartbeat",
                    "id: abc123",
                    "event: workspace_log",
                    'data: {"severity_text":"INFO",',
                    'data: "event_category":"file"}',
                    "",
                ]
            )
        )
    )

    assert events == [
        {
            "id": "abc123",
            "event": "workspace_log",
            "data": {"severity_text": "INFO", "event_category": "file"},
        }
    ]


def test_workspace_log_worker_never_calls_tk_after_from_its_thread():
    main_thread = threading.get_ident()

    class Root:
        def __init__(self):
            self.after_threads = []

        def after(self, _delay, _callback):
            self.after_threads.append(threading.get_ident())
            return "drain-job"

        def after_cancel(self, _job):
            pass

    root = Root()
    view = WorkspaceLogView(
        root=root,
        stream_reader=lambda _cursor: iter(
            [{"id": "evt-1", "event": "workspace_log", "data": {"chat_id": "chat-a"}}]
        ),
        on_new_activity=lambda _chat_id: None,
    )

    view.start_stream()
    view.stop_event.wait(0.01)
    view.close()
    assert view.thread is not None
    view.thread.join(timeout=1)

    assert root.after_threads
    assert root.after_threads == [main_thread]


def test_workspace_log_queue_poller_delivers_events_and_close_cancels_late_delivery():
    arrived = threading.Event()
    delivered = []

    class Root:
        def __init__(self):
            self.callbacks = {}
            self.cancelled = set()
            self.next_job = 0

        def after(self, _delay, callback):
            self.next_job += 1
            self.callbacks[self.next_job] = callback
            return self.next_job

        def after_cancel(self, job):
            self.cancelled.add(job)

        def run_pending(self):
            for job, callback in list(self.callbacks.items()):
                del self.callbacks[job]
                if job not in self.cancelled:
                    callback()

    def stream(_cursor):
        arrived.set()
        yield {"id": "evt-1", "event": "workspace_log", "data": {"chat_id": "chat-a"}}
        while True:
            time.sleep(0.001)

    root = Root()
    view = WorkspaceLogView(root=root, stream_reader=stream, on_new_activity=delivered.append)
    view.start_stream()
    assert arrived.wait(timeout=1)
    for _ in range(50):
        if not view.event_queue.empty():
            break
        time.sleep(0.002)

    root.run_pending()

    assert [(notice.chat_id, notice.operation_id) for notice in delivered] == [
        ("chat-a", "evt-1")
    ]
    assert view.last_event_id == "evt-1"
    assert view.drain_job is not None

    view.close()
    view.event_queue.put(("event", {"id": "evt-late", "event": "workspace_log", "data": {"chat_id": "chat-late"}}))
    root.run_pending()
    assert [(notice.chat_id, notice.operation_id) for notice in delivered] == [
        ("chat-a", "evt-1")
    ]
