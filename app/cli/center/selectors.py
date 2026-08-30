"""Derived read-model selectors for BQA Center views."""

from __future__ import annotations

from app.cli.center.models import LogRecord, Operation, Session
from app.cli.center.state import CenterState


def visible_sessions(state: CenterState, query: str = "") -> list[Session]:
    wanted = query.strip().lower()
    result: list[Session] = []
    for chat_id in state.sessions.order:
        session = state.sessions.by_id.get(chat_id)
        if session is None or chat_id in state.sessions.closed_ids:
            continue
        if chat_id not in state.sessions.visible_ids and not session.visible:
            continue
        if wanted and wanted not in chat_id.lower():
            continue
        result.append(session)
    return result


def visible_operations(state: CenterState, query: str = "") -> list[Operation]:
    selected = state.sessions.selected_id
    wanted = query.strip().lower()
    rows: list[Operation] = []
    for operation_id in reversed(state.operations.order):
        operation = state.operations.by_id.get(operation_id)
        if operation is None:
            continue
        if selected and operation.chat_id != selected:
            continue
        haystack = " ".join(
            (
                operation.command,
                operation.chat_id,
                operation.status.value,
                operation.cwd,
                operation.stdout,
                operation.stderr,
            )
        ).lower()
        if wanted and wanted not in haystack:
            continue
        rows.append(operation)
    return rows


def visible_logs(state: CenterState, *, limit: int = 500) -> list[LogRecord]:
    severity = state.logs.severity_filter.strip().lower()
    chat = state.logs.chat_filter.strip().lower()
    outcome = state.logs.outcome_filter.strip().lower()
    category = state.logs.category_filter.strip().lower()
    query = state.logs.search_query.strip().lower()
    rows: list[LogRecord] = []
    for event_id in reversed(state.logs.order):
        row = state.logs.by_id.get(event_id)
        if row is None:
            continue
        if severity not in {"", "all"} and row.severity.lower() != severity:
            continue
        if chat and chat not in row.chat_id.lower():
            continue
        if outcome not in {"", "all"} and row.outcome != outcome:
            continue
        if category not in {"", "all"} and row.category != category:
            continue
        if query:
            haystack = " ".join(
                (
                    row.action,
                    row.chat_id,
                    row.category,
                    row.outcome,
                    row.message,
                    row.operation_id,
                )
            ).lower()
            if query not in haystack:
                continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows
