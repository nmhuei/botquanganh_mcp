"""Canonical BQA Center domain models, independent from Tk widgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OperationStatus(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


TERMINAL_OPERATION_STATUSES = frozenset(
    {
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.TIMED_OUT,
        OperationStatus.CANCELLED,
    }
)


class StreamPhase(StrEnum):
    OFFLINE = "offline"
    CONNECTING = "connecting"
    REPLAYING = "replaying"
    LIVE = "live"
    STALE = "stale"
    RETRY_WAIT = "retry_wait"
    RESYNCING = "resyncing"


class ActionStatus(StrEnum):
    IDLE = "idle"
    REQUESTED = "requested"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Session:
    chat_id: str
    created_at: float
    path: str = ""
    last_activity_at: float = 0.0
    operation_count: int = 0
    running_count: int = 0
    failed_count: int = 0
    unread_count: int = 0
    tracking: bool = True
    visible: bool = False
    closed: bool = False


@dataclass(frozen=True)
class Operation:
    operation_id: str
    chat_id: str = ""
    event_id: str = ""
    command: str = ""
    cwd: str = ""
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    duration_ms: float | None = None
    status: OperationStatus = OperationStatus.DISCOVERED
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    source: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LogRecord:
    event_id: str
    timestamp: str = ""
    observed_timestamp: float = 0.0
    operation_id: str = ""
    chat_id: str = ""
    severity: str = "INFO"
    category: str = "api"
    outcome: str = "unknown"
    action: str = ""
    phase: str = ""
    duration_ms: float | None = None
    source: str = ""
    message: str = ""
    payload: Any = None


@dataclass(frozen=True)
class RuntimeSnapshot:
    bridge: str = "unknown"
    server_running: bool = False
    server_pid: int | None = None
    tunnel_running: bool = False
    tunnel_pid: int | None = None
    connector_ready: bool = False
    connector_url: str = ""
    auth_required: bool = False
    workspace: str = ""
    last_updated_at: float = 0.0
    stale: bool = False
    error: str = ""


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str
    group: str
    status: ActionStatus = ActionStatus.IDLE
    requested_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    message: str = ""
    error: str = ""
