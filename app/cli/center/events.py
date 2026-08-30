"""Typed events and intents consumed by the BQA Center reducer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    event_id: str = ""


@dataclass(frozen=True)
class RuntimeSnapshotReceived(Event):
    data: dict[str, Any] | None = None
    observed_at: float = 0.0


@dataclass(frozen=True)
class RuntimeSnapshotFailed(Event):
    error: str = ""
    observed_at: float = 0.0


@dataclass(frozen=True)
class StreamStateChanged(Event):
    phase: str = "offline"
    last_event_id: str = ""
    observed_at: float = 0.0
    retry_after_ms: int = 0
    error: str = ""


@dataclass(frozen=True)
class SessionDiscovered(Event):
    chat_id: str = ""
    created_at: float = 0.0
    last_activity_at: float = 0.0
    path: str = ""


@dataclass(frozen=True)
class SessionRemoved(Event):
    chat_id: str = ""


@dataclass(frozen=True)
class SessionSelected(Event):
    chat_id: str | None = None


@dataclass(frozen=True)
class SessionRevealed(Event):
    chat_id: str = ""


@dataclass(frozen=True)
class SessionClosed(Event):
    chat_id: str = ""


@dataclass(frozen=True)
class SessionTrackingChanged(Event):
    chat_id: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class SessionActivityObserved(Event):
    chat_id: str = ""
    operation_id: str = ""
    observed_at: float = 0.0


@dataclass(frozen=True)
class OperationObserved(Event):
    operation_id: str = ""
    chat_id: str = ""
    phase: str = ""
    status: str = ""
    timestamp: float = 0.0
    command: str = ""
    cwd: str = ""
    exit_code: int | None = None
    duration_ms: float | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    source: str = ""
    attributes: dict[str, Any] | None = None
    reveal_session: bool = True
    count_unread: bool = True


@dataclass(frozen=True)
class WorkspaceLogObserved(Event):
    payload: dict[str, Any] | None = None
    observed_at: float = 0.0


@dataclass(frozen=True)
class LogsFilterChanged(Event):
    severity: str | None = None
    chat: str | None = None
    outcome: str | None = None
    category: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class LogsViewportChanged(Event):
    at_bottom: bool = True


@dataclass(frozen=True)
class LogsJumpToLatest(Event):
    pass


@dataclass(frozen=True)
class ActivityViewportChanged(Event):
    at_bottom: bool = True


@dataclass(frozen=True)
class ActivityJumpToLatest(Event):
    pass


@dataclass(frozen=True)
class UiPreferenceChanged(Event):
    key: str = ""
    value: Any = None


@dataclass(frozen=True)
class TabSelected(Event):
    tab: str = "runtime"


@dataclass(frozen=True)
class CompactModeChanged(Event):
    compact: bool = False


@dataclass(frozen=True)
class ActionRequested(Event):
    action_id: str = ""
    kind: str = ""
    group: str = ""


@dataclass(frozen=True)
class ActionStarted(Event):
    action_id: str = ""
    observed_at: float = 0.0


@dataclass(frozen=True)
class ActionFinished(Event):
    action_id: str = ""
    ok: bool = True
    observed_at: float = 0.0
    message: str = ""
    error: str = ""
