"""Pure-ish state transitions for the BQA Center canonical state."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.cli.center.events import (
    ActionFinished,
    ActionRequested,
    ActionStarted,
    ActivityJumpToLatest,
    ActivityViewportChanged,
    CompactModeChanged,
    Event,
    LogsFilterChanged,
    LogsJumpToLatest,
    LogsViewportChanged,
    OperationObserved,
    RuntimeSnapshotFailed,
    RuntimeSnapshotReceived,
    SessionActivityObserved,
    SessionClosed,
    SessionDiscovered,
    SessionRemoved,
    SessionRevealed,
    SessionSelected,
    SessionTrackingChanged,
    StreamStateChanged,
    TabSelected,
    UiPreferenceChanged,
    WorkspaceLogObserved,
)
from app.cli.center.models import (
    Action,
    ActionStatus,
    LogRecord,
    Operation,
    OperationStatus,
    RuntimeSnapshot,
    Session,
    StreamPhase,
    TERMINAL_OPERATION_STATUSES,
)
from app.cli.center.state import CenterState


LOG_CACHE_LIMIT = 5000
OPERATION_CACHE_LIMIT = 10000


def _operation_status(raw: str) -> OperationStatus:
    value = str(raw or "").strip().lower()
    aliases = {
        "success": "succeeded",
        "complete": "succeeded",
        "completed": "succeeded",
        "failure": "failed",
        "timeout": "timed_out",
        "canceled": "cancelled",
    }
    value = aliases.get(value, value)
    try:
        return OperationStatus(value)
    except ValueError:
        return OperationStatus.DISCOVERED


def _runtime_snapshot(data: dict[str, Any], observed_at: float) -> RuntimeSnapshot:
    server = data.get("server") or {}
    tunnel = data.get("tunnel") or {}
    return RuntimeSnapshot(
        bridge=str(data.get("bridge") or "unknown"),
        server_running=bool(server.get("running")),
        server_pid=server.get("pid"),
        tunnel_running=bool(tunnel.get("running")),
        tunnel_pid=tunnel.get("pid"),
        connector_ready=bool(data.get("connector_ready")),
        connector_url=str(data.get("url") or data.get("last_known_url") or ""),
        auth_required=bool(data.get("auth_required")),
        workspace=str(data.get("workspace") or ""),
        last_updated_at=observed_at,
        stale=False,
        error="",
    )


def _ensure_session(state: CenterState, chat_id: str, timestamp: float = 0.0) -> Session:
    existing = state.sessions.by_id.get(chat_id)
    if existing is not None:
        return existing
    session = Session(chat_id=chat_id, created_at=timestamp, last_activity_at=timestamp)
    state.sessions.by_id[chat_id] = session
    state.sessions.order.append(chat_id)
    state.sessions.order.sort(
        key=lambda item: (state.sessions.by_id[item].created_at, item)
    )
    return session


def _session_operation_delta(
    state: CenterState,
    *,
    previous: Operation | None,
    current: Operation,
    reveal_session: bool = True,
    count_unread: bool = True,
) -> None:
    if not current.chat_id:
        return
    session = _ensure_session(state, current.chat_id, current.created_at)
    operation_count = session.operation_count
    running_count = session.running_count
    failed_count = session.failed_count

    if previous is None:
        operation_count += 1
        if current.status == OperationStatus.RUNNING:
            running_count += 1
        if current.status in {OperationStatus.FAILED, OperationStatus.TIMED_OUT}:
            failed_count += 1
    else:
        if previous.status == OperationStatus.RUNNING and current.status != OperationStatus.RUNNING:
            running_count = max(0, running_count - 1)
        elif previous.status != OperationStatus.RUNNING and current.status == OperationStatus.RUNNING:
            running_count += 1
        if previous.status not in {OperationStatus.FAILED, OperationStatus.TIMED_OUT} and current.status in {
            OperationStatus.FAILED,
            OperationStatus.TIMED_OUT,
        }:
            failed_count += 1

    unread_count = session.unread_count
    if count_unread and state.sessions.selected_id != current.chat_id:
        unread_count += 1

    state.sessions.by_id[current.chat_id] = replace(
        session,
        last_activity_at=max(session.last_activity_at, current.finished_at or current.started_at or current.created_at),
        operation_count=operation_count,
        running_count=running_count,
        failed_count=failed_count,
        unread_count=unread_count,
        visible=session.visible or reveal_session,
        closed=False if reveal_session else session.closed,
    )
    if reveal_session:
        state.sessions.visible_ids.add(current.chat_id)
        state.sessions.closed_ids.discard(current.chat_id)
        if state.sessions.selected_id is None:
            state.sessions.selected_id = current.chat_id
            state.sessions.by_id[current.chat_id] = replace(
                state.sessions.by_id[current.chat_id],
                unread_count=0,
            )


def reduce_event(state: CenterState, event: Event) -> CenterState:
    """Mutate and return the canonical state for one normalized event."""
    state.diagnostics.events_received_total += 1

    if isinstance(event, RuntimeSnapshotReceived):
        data = event.data or {}
        state.runtime.snapshot = _runtime_snapshot(data, event.observed_at)
        state.runtime.last_success_at = event.observed_at
        state.runtime.last_error = ""
        return state

    if isinstance(event, RuntimeSnapshotFailed):
        state.runtime.last_error = event.error
        state.runtime.snapshot = replace(
            state.runtime.snapshot,
            stale=True,
            error=event.error,
        )
        return state

    if isinstance(event, StreamStateChanged):
        try:
            phase = StreamPhase(event.phase)
        except ValueError:
            phase = StreamPhase.OFFLINE
        state.stream.phase = phase
        state.stream.last_event_id = event.last_event_id or state.stream.last_event_id
        state.stream.last_receive_monotonic = event.observed_at or state.stream.last_receive_monotonic
        state.stream.retry_after_ms = max(0, int(event.retry_after_ms or 0))
        state.stream.error = event.error
        state.stream.replaying = phase == StreamPhase.REPLAYING
        if phase == StreamPhase.LIVE:
            state.stream.reconnect_attempt = 0
        elif phase in {StreamPhase.RETRY_WAIT, StreamPhase.CONNECTING} and event.error:
            state.stream.reconnect_attempt += 1
            state.diagnostics.stream_reconnect_count += 1
        return state

    if isinstance(event, SessionDiscovered):
        existing = state.sessions.by_id.get(event.chat_id)
        if existing is None:
            state.sessions.by_id[event.chat_id] = Session(
                chat_id=event.chat_id,
                created_at=event.created_at,
                path=event.path,
                last_activity_at=event.last_activity_at,
                tracking=True,
            )
            state.sessions.tracking_ids.add(event.chat_id)
        else:
            state.sessions.by_id[event.chat_id] = replace(
                existing,
                created_at=event.created_at or existing.created_at,
                path=event.path or existing.path,
                last_activity_at=max(existing.last_activity_at, event.last_activity_at),
            )
        if event.chat_id not in state.sessions.order:
            state.sessions.order.append(event.chat_id)
        state.sessions.order.sort(
            key=lambda item: (state.sessions.by_id[item].created_at, item)
        )
        return state

    if isinstance(event, SessionRemoved):
        state.sessions.by_id.pop(event.chat_id, None)
        state.sessions.visible_ids.discard(event.chat_id)
        state.sessions.closed_ids.discard(event.chat_id)
        state.sessions.tracking_ids.discard(event.chat_id)
        state.sessions.disabled_ids.discard(event.chat_id)
        state.sessions.order = [item for item in state.sessions.order if item != event.chat_id]
        if state.sessions.selected_id == event.chat_id:
            state.sessions.selected_id = None
        return state

    if isinstance(event, SessionSelected):
        if event.chat_id is None:
            state.sessions.selected_id = None
            return state
        if event.chat_id in state.sessions.by_id:
            state.sessions.selected_id = event.chat_id
            session = state.sessions.by_id[event.chat_id]
            state.sessions.by_id[event.chat_id] = replace(session, unread_count=0)
        return state

    if isinstance(event, SessionRevealed):
        session = _ensure_session(state, event.chat_id)
        state.sessions.visible_ids.add(event.chat_id)
        state.sessions.closed_ids.discard(event.chat_id)
        state.sessions.by_id[event.chat_id] = replace(session, visible=True, closed=False)
        if state.sessions.selected_id is None:
            state.sessions.selected_id = event.chat_id
        return state

    if isinstance(event, SessionClosed):
        if event.chat_id in state.sessions.by_id:
            state.sessions.closed_ids.add(event.chat_id)
            state.sessions.visible_ids.discard(event.chat_id)
            state.sessions.by_id[event.chat_id] = replace(
                state.sessions.by_id[event.chat_id],
                visible=False,
                closed=True,
            )
            if state.sessions.selected_id == event.chat_id:
                state.sessions.selected_id = None
        return state

    if isinstance(event, SessionTrackingChanged):
        session = _ensure_session(state, event.chat_id)
        if event.enabled:
            state.sessions.tracking_ids.add(event.chat_id)
            state.sessions.disabled_ids.discard(event.chat_id)
        else:
            state.sessions.tracking_ids.discard(event.chat_id)
            state.sessions.disabled_ids.add(event.chat_id)
        state.sessions.by_id[event.chat_id] = replace(session, tracking=event.enabled)
        return state

    if isinstance(event, SessionActivityObserved):
        session = _ensure_session(state, event.chat_id, event.observed_at)
        unread = session.unread_count
        if state.sessions.selected_id != event.chat_id:
            unread += 1
        state.sessions.by_id[event.chat_id] = replace(
            session,
            last_activity_at=max(session.last_activity_at, event.observed_at),
            unread_count=unread,
            visible=True,
            closed=False,
        )
        state.sessions.visible_ids.add(event.chat_id)
        state.sessions.closed_ids.discard(event.chat_id)
        if state.sessions.selected_id is None:
            state.sessions.selected_id = event.chat_id
            state.sessions.by_id[event.chat_id] = replace(
                state.sessions.by_id[event.chat_id],
                unread_count=0,
            )
        return state

    if isinstance(event, OperationObserved):
        previous = state.operations.by_id.get(event.operation_id)
        incoming = _operation_status(event.status)
        if previous is not None and previous.status in TERMINAL_OPERATION_STATUSES:
            if incoming not in TERMINAL_OPERATION_STATUSES:
                return state
            if previous.status == incoming:
                return state

        created_at = (
            previous.created_at
            if previous is not None and previous.created_at
            else event.timestamp
        )
        started_at = previous.started_at if previous else None
        finished_at = previous.finished_at if previous else None
        if incoming == OperationStatus.RUNNING:
            started_at = started_at or event.timestamp
        if incoming in TERMINAL_OPERATION_STATUSES:
            finished_at = event.timestamp or finished_at

        operation = Operation(
            operation_id=event.operation_id,
            chat_id=event.chat_id or (previous.chat_id if previous else ""),
            event_id=event.event_id or (previous.event_id if previous else ""),
            command=event.command or (previous.command if previous else ""),
            cwd=event.cwd or (previous.cwd if previous else ""),
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=event.duration_ms if event.duration_ms is not None else (previous.duration_ms if previous else None),
            status=incoming,
            exit_code=event.exit_code if event.exit_code is not None else (previous.exit_code if previous else None),
            stdout=event.stdout or (previous.stdout if previous else ""),
            stderr=event.stderr or (previous.stderr if previous else ""),
            error=event.error or (previous.error if previous else ""),
            source=event.source or (previous.source if previous else ""),
            attributes={**(previous.attributes if previous else {}), **(event.attributes or {})},
        )
        state.operations.by_id[event.operation_id] = operation
        if event.operation_id not in state.operations.order:
            state.operations.order.append(event.operation_id)
        if len(state.operations.order) > OPERATION_CACHE_LIMIT:
            removed = state.operations.order[:-OPERATION_CACHE_LIMIT]
            state.operations.order = state.operations.order[-OPERATION_CACHE_LIMIT:]
            for operation_id in removed:
                if operation_id != state.operations.selected_id:
                    state.operations.by_id.pop(operation_id, None)
        _session_operation_delta(
            state,
            previous=previous,
            current=operation,
            reveal_session=event.reveal_session,
            count_unread=event.count_unread,
        )
        if not state.ui.activity_at_bottom:
            state.ui.activity_unseen_count += 1
        return state

    if isinstance(event, WorkspaceLogObserved):
        payload = event.payload or {}
        event_id = str(event.event_id or payload.get("event_id") or payload.get("interaction_id") or "")
        if not event_id:
            return state
        if event_id in state.logs.by_id:
            return state
        duration_raw = payload.get("event_duration_ms")
        try:
            duration = float(duration_raw) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration = None
        record = LogRecord(
            event_id=event_id,
            timestamp=str(payload.get("ts") or ""),
            observed_timestamp=event.observed_at,
            operation_id=str(payload.get("operation_id") or payload.get("interaction_id") or ""),
            chat_id=str(payload.get("chat_id") or ""),
            severity=str(payload.get("severity_text") or "INFO").upper(),
            category=str(payload.get("event_category") or "api").lower(),
            outcome=str(payload.get("event_outcome") or "unknown").lower(),
            action=str(payload.get("event_action") or payload.get("kind") or ""),
            phase=str(payload.get("operation_phase") or "").lower(),
            duration_ms=duration,
            source=str(payload.get("log_source") or payload.get("source") or ""),
            message=str(payload.get("message") or ""),
            payload=payload.get("payload"),
        )
        state.logs.by_id[event_id] = record
        state.logs.order.append(event_id)
        if len(state.logs.order) > LOG_CACHE_LIMIT:
            removed = state.logs.order[:-LOG_CACHE_LIMIT]
            state.logs.order = state.logs.order[-LOG_CACHE_LIMIT:]
            for old_id in removed:
                if old_id != state.logs.selected_event_id:
                    state.logs.by_id.pop(old_id, None)
        if not state.logs.at_bottom:
            state.logs.unseen_count += 1
        return state

    if isinstance(event, LogsFilterChanged):
        if event.severity is not None:
            state.logs.severity_filter = event.severity
        if event.chat is not None:
            state.logs.chat_filter = event.chat
        if event.outcome is not None:
            state.logs.outcome_filter = event.outcome
        if event.category is not None:
            state.logs.category_filter = event.category
        if event.query is not None:
            state.logs.search_query = event.query
        return state

    if isinstance(event, LogsViewportChanged):
        state.logs.at_bottom = event.at_bottom
        if event.at_bottom:
            state.logs.unseen_count = 0
        return state

    if isinstance(event, LogsJumpToLatest):
        state.logs.at_bottom = True
        state.logs.auto_follow = True
        state.logs.unseen_count = 0
        return state

    if isinstance(event, ActivityViewportChanged):
        state.ui.activity_at_bottom = event.at_bottom
        if event.at_bottom:
            state.ui.activity_unseen_count = 0
        return state

    if isinstance(event, ActivityJumpToLatest):
        state.ui.activity_at_bottom = True
        state.ui.activity_auto_follow = True
        state.ui.activity_unseen_count = 0
        return state

    if isinstance(event, UiPreferenceChanged):
        if hasattr(state.ui, event.key):
            setattr(state.ui, event.key, event.value)
        return state

    if isinstance(event, TabSelected):
        state.ui.active_tab = event.tab
        return state

    if isinstance(event, CompactModeChanged):
        state.ui.compact_mode = event.compact
        return state

    if isinstance(event, ActionRequested):
        state.actions.by_id[event.action_id] = Action(
            action_id=event.action_id,
            kind=event.kind,
            group=event.group,
            status=ActionStatus.REQUESTED,
        )
        return state

    if isinstance(event, ActionStarted):
        action = state.actions.by_id.get(event.action_id)
        if action is not None:
            state.actions.by_id[event.action_id] = replace(
                action,
                status=ActionStatus.RUNNING,
                started_at=event.observed_at,
            )
            state.actions.running_groups.add(action.group)
        return state

    if isinstance(event, ActionFinished):
        action = state.actions.by_id.get(event.action_id)
        if action is not None:
            state.actions.by_id[event.action_id] = replace(
                action,
                status=ActionStatus.SUCCEEDED if event.ok else ActionStatus.FAILED,
                finished_at=event.observed_at,
                message=event.message,
                error=event.error,
            )
            state.actions.running_groups.discard(action.group)
        return state

    return state
