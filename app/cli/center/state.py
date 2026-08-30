"""Canonical CenterState and its independent sub-states."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.cli.center.models import (
    Action,
    LogRecord,
    Operation,
    RuntimeSnapshot,
    Session,
    StreamPhase,
)


@dataclass
class SessionsState:
    by_id: dict[str, Session] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    selected_id: str | None = None
    visible_ids: set[str] = field(default_factory=set)
    closed_ids: set[str] = field(default_factory=set)
    tracking_ids: set[str] = field(default_factory=set)
    disabled_ids: set[str] = field(default_factory=set)


@dataclass
class OperationsState:
    by_id: dict[str, Operation] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    selected_id: str | None = None


@dataclass
class LogsState:
    by_id: dict[str, LogRecord] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    selected_event_id: str | None = None
    severity_filter: str = "all"
    chat_filter: str = ""
    outcome_filter: str = "all"
    category_filter: str = "all"
    search_query: str = ""
    auto_follow: bool = True
    at_bottom: bool = True
    unseen_count: int = 0


@dataclass
class RuntimeState:
    snapshot: RuntimeSnapshot = field(default_factory=RuntimeSnapshot)
    last_success_at: float = 0.0
    last_error: str = ""


@dataclass
class StreamState:
    phase: StreamPhase = StreamPhase.OFFLINE
    last_event_id: str = ""
    last_event_at: float = 0.0
    last_receive_monotonic: float = 0.0
    reconnect_attempt: int = 0
    retry_after_ms: int = 0
    replaying: bool = False
    error: str = ""


@dataclass
class UiState:
    language: str = "en"
    theme: str = "system"
    font_scale: float = 1.0
    density: str = "comfortable"
    active_tab: str = "runtime"
    compact_mode: bool = False
    activity_query: str = ""
    activity_sort_key: str = ""
    activity_sort_descending: bool = False
    activity_auto_follow: bool = True
    activity_at_bottom: bool = True
    activity_unseen_count: int = 0
    session_pane_collapsed: bool = False


@dataclass
class ActionsState:
    by_id: dict[str, Action] = field(default_factory=dict)
    running_groups: set[str] = field(default_factory=set)


@dataclass
class DiagnosticsState:
    events_received_total: int = 0
    events_duplicate_total: int = 0
    events_coalesced_total: int = 0
    events_dropped_total: int = 0
    queue_depth: int = 0
    queue_high_watermark: int = 0
    render_batch_count: int = 0
    render_batch_size: int = 0
    render_duration_ms: float = 0.0
    stream_reconnect_count: int = 0


@dataclass
class CenterState:
    runtime: RuntimeState = field(default_factory=RuntimeState)
    stream: StreamState = field(default_factory=StreamState)
    sessions: SessionsState = field(default_factory=SessionsState)
    operations: OperationsState = field(default_factory=OperationsState)
    logs: LogsState = field(default_factory=LogsState)
    ui: UiState = field(default_factory=UiState)
    actions: ActionsState = field(default_factory=ActionsState)
    diagnostics: DiagnosticsState = field(default_factory=DiagnosticsState)
