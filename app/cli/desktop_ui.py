"""Native Python desktop control center for BotQuangAnh Host MCP."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.activity_log import read_mcp_command_activity
from app.cli.client import RESTClient
from app.cli.config_view import set_workspace_config
from app.cli.context import CLIContext
from app.cli.lifecycle import (
    process_command_line,
    read_pid,
    restart,
    start,
    status_data,
)

StatusReader = Callable[[Any, dict[str, str]], dict[str, Any]]
LifecycleAction = Callable[..., dict[str, Any]]
ActivityReader = Callable[[int], list[dict[str, Any]]]
StreamJobsReader = Callable[[], Any]
WorkspaceLogStreamReader = Callable[[str | None], Iterator[dict[str, Any]]]

BQA_UI_DAEMON_ENV = "BQA_UI_DAEMON"
DESKTOP_UI_PID_FILENAME = "desktop-ui.pid"
BACKEND_ALIVE_BADGE = ("backend: ● alive", "#147a45")
BACKEND_DOWN_BADGE = ("backend: ○ down", "#64748b")
MIN_COMPLETION_TOAST_SECONDS = 10.0
COMPLETION_TOAST_LIFETIME_MS = 6000
STREAM_JOBS_PATH = "/api/v1/jobs"
STREAM_JOBS_LIMIT = 100
STREAM_DEFAULT_CHIP = "all"
STREAM_CHIP_KEYS = ("all", "running", "done", "error")
STREAM_CHIP_LABELS = ("ALL", "RUNNING", "DONE", "ERROR")
STREAM_STATUS_GLYPHS = {"running": "●", "done": "✓", "error": "✗", "queued": "◔"}
STREAM_UNKNOWN_GLYPH = "·"
STREAM_EMPTY_MESSAGE = "Chưa có job nào trong luồng."
WORKSPACE_LOG_STREAM_PATH = "/api/v1/activity/stream"
WORKSPACE_LOG_REPLAY = 100
WORKSPACE_LOG_CACHE_LIMIT = 500
WORKSPACE_LOG_DEFAULT_CHIP = "all"
WORKSPACE_LOG_CHIP_KEYS = ("all", "error", "process", "file", "session")
WORKSPACE_LOG_CHIP_LABELS = ("ALL", "ERROR", "PROCESS", "FILE", "SESSION")
WORKSPACE_LOG_RECONNECT_SECONDS = 2.0
WORKSPACE_LOG_EMPTY_MESSAGE = "Chưa có workspace log phù hợp bộ lọc."


class DesktopUIUnavailable(RuntimeError):
    """Raised when the current session cannot create a desktop window."""


class DesktopUILaunchError(RuntimeError):
    """Raised when a detached desktop window cannot be started."""


class DesktopUIAlreadyRunning(RuntimeError):
    """Raised when a live detached desktop window already owns the session."""

    def __init__(self, pid: int) -> None:
        super().__init__(f"BQA Control Center đã chạy nền (PID {pid}).")
        self.pid = pid


def backend_badge(data: dict[str, Any]) -> tuple[str, str]:
    """Derive the backend liveness badge from the same data as `bqa status`."""
    if (data.get("server") or {}).get("running"):
        return BACKEND_ALIVE_BADGE
    return BACKEND_DOWN_BADGE


def completion_fingerprint(data: dict[str, Any]) -> str:
    """Hash the runtime-relevant status fields used for done-transition diffing."""
    server = data.get("server") or {}
    tunnel = data.get("tunnel") or {}
    payload = {
        "ok": bool(data.get("ok")),
        "bridge": str(data.get("bridge", "")),
        "server_running": bool(server.get("running")),
        "server_pid": server.get("pid"),
        "tunnel_running": bool(tunnel.get("running")),
        "url_state": str(data.get("url_state", "")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def completion_toast_due(
    elapsed_seconds: float,
    start_fingerprint: str | None,
    current_fingerprint: str,
    last_fired_fingerprint: str | None,
) -> bool:
    """One-shot gate for the completion toast.

    Fires only when the tracked operation ran at least
    ``MIN_COMPLETION_TOAST_SECONDS``, the runtime fingerprint changed since
    the operation started (running -> done), and this exact completion has
    not been toasted before.
    """
    if elapsed_seconds < MIN_COMPLETION_TOAST_SECONDS:
        return False
    if start_fingerprint is not None and current_fingerprint == start_fingerprint:
        return False
    return current_fingerprint != last_fired_fingerprint


@dataclass(frozen=True)
class StreamRow:
    """Display model for one row of the desktop activity stream panel."""

    job_id: str
    op: str = ""
    status: str = ""
    chat_id: str = ""
    created_at: float | None = None
    detail: str = ""
    result_excerpt: str = ""


@dataclass(frozen=True)
class WorkspaceLogRow:
    """Normalized display model for one workspace journal event."""

    event_id: str
    timestamp: str = ""
    severity: str = "INFO"
    category: str = "api"
    action: str = ""
    outcome: str = "unknown"
    phase: str = ""
    chat_id: str = ""
    duration_ms: float | None = None
    interaction_id: str = ""
    dataset: str = ""
    source: str = ""
    payload: Any = None


def clip_text(value: Any, limit: int) -> str:
    """Collapse whitespace and hard-clip to ``limit`` characters."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def normalize_stream_status(value: Any) -> str:
    return str(value or "").strip().lower()


def stream_status_glyph(status: Any) -> str:
    return STREAM_STATUS_GLYPHS.get(normalize_stream_status(status), STREAM_UNKNOWN_GLYPH)


def format_stream_time(value: Any) -> str:
    """Render an epoch timestamp as UTC; anything unparsable becomes a dash."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(number)))
    except (OverflowError, OSError, ValueError):
        return "—"


def stream_row_from_mapping(entry: Any) -> StreamRow | None:
    """Build a display row from one job record; non-mappings are skipped."""
    if not isinstance(entry, dict):
        return None
    created_raw = entry.get("created_at")
    created_at: float | None
    try:
        created_at = float(created_raw) if created_raw is not None else None
    except (TypeError, ValueError):
        created_at = None
    return StreamRow(
        job_id=str(entry.get("job_id") or ""),
        op=str(entry.get("op") or ""),
        status=normalize_stream_status(entry.get("status")),
        chat_id=str(entry.get("chat_id") or ""),
        created_at=created_at,
        detail=str(entry.get("detail") or ""),
        result_excerpt=str(entry.get("result_excerpt") or ""),
    )


def stream_rows_from_payload(payload: Any) -> list[StreamRow]:
    """Parse a /api/v1/jobs envelope defensively; garbage yields no rows."""
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return []
    rows: list[StreamRow] = []
    for entry in jobs:
        row = stream_row_from_mapping(entry)
        if row is not None:
            rows.append(row)
    return rows


def normalize_stream_chip(value: Any) -> str | None:
    """Map a chip click to its filter key; unknown chips change nothing."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in STREAM_CHIP_KEYS else None


def stream_row_matches_chip(row: StreamRow, chip: str) -> bool:
    # Unknown-status rows only ever surface under ALL.
    if chip == STREAM_DEFAULT_CHIP:
        return True
    return row.status == chip


def filter_stream_rows(rows: Sequence[StreamRow], chip: str) -> list[StreamRow]:
    return [row for row in rows if stream_row_matches_chip(row, chip)]


def shifted_selection(order: Sequence[str], current: str | None, delta: int) -> str | None:
    """Next iid after moving ``delta`` steps, clamped to the visible range."""
    if not order:
        return None
    if current in order:
        index = order.index(current) + delta
    else:
        index = 0 if delta >= 0 else len(order) - 1
    index = max(0, min(len(order) - 1, index))
    return order[index]


def reduce_stream_view(
    rows: Sequence[StreamRow],
    *,
    chip: str,
    error_message: str = "",
) -> tuple[list[StreamRow], str]:
    """Resolve the panel state: filtered rows plus the muted notice line.

    A fetch error always wins and clears previous rows so a dead backend
    degrades to a single muted line instead of stale data.
    """
    if error_message:
        return [], error_message
    visible = filter_stream_rows(rows, chip)
    if not visible:
        return [], STREAM_EMPTY_MESSAGE
    return list(visible), ""


def stream_error_message(exc: BaseException) -> str:
    return clip_text(f"Không đọc được luồng job: {exc}", 180)


def stream_copy_line(row: StreamRow) -> str:
    parts = [row.op or "?", row.status or "?", row.job_id or "?"]
    if row.chat_id:
        parts.append(row.chat_id)
    return " ".join(parts)


def format_stream_details(row: StreamRow) -> str:
    lines = [
        f"Job: {row.job_id or '—'}",
        f"Op: {row.op or '—'}",
        f"Status: {stream_status_glyph(row.status)} {row.status or '—'}",
        f"Created: {format_stream_time(row.created_at)}",
        f"Chat: {row.chat_id or '—'}",
        "",
        "Detail:",
        row.detail or "(empty)",
        "",
        "Result:",
        row.result_excerpt or "(empty)",
        "",
        f"Copy: {stream_copy_line(row)}",
    ]
    return "\n".join(lines)


def make_stream_jobs_reader(ctx: CLIContext, *, limit: int = STREAM_JOBS_LIMIT) -> StreamJobsReader:
    """Default stream reader following the CLI REST client conventions."""
    values = getattr(ctx, "values", {}) or {}
    connect_host = str(values.get("MCP_CONNECT_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    if connect_host in {"0.0.0.0", "::"}:  # nosec B104
        connect_host = "127.0.0.1"
    port = str(values.get("MCP_PORT", "18427")).strip() or "18427"
    base_url = str(getattr(ctx, "base_url", "") or "").rstrip("/") or f"http://{connect_host}:{port}"
    token = str(getattr(ctx, "token", "") or "")
    timeout = float(getattr(ctx, "request_timeout", 15.0) or 15.0)
    client = RESTClient(base_url, token=token, timeout=timeout)

    def reader() -> Any:
        return client.get(STREAM_JOBS_PATH, query={"limit": limit})

    return reader


def workspace_log_row_from_mapping(entry: Any, *, event_id: str = "") -> WorkspaceLogRow | None:
    if not isinstance(entry, dict):
        return None
    duration_raw = entry.get("event_duration_ms")
    try:
        duration = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None
    return WorkspaceLogRow(
        event_id=str(event_id or entry.get("event_id") or entry.get("interaction_id") or ""),
        timestamp=str(entry.get("ts") or ""),
        severity=str(entry.get("severity_text") or "INFO").upper(),
        category=str(entry.get("event_category") or "api").lower(),
        action=str(entry.get("event_action") or entry.get("kind") or ""),
        outcome=str(entry.get("event_outcome") or "unknown").lower(),
        phase=str(entry.get("operation_phase") or "").lower(),
        chat_id=str(entry.get("chat_id") or ""),
        duration_ms=duration,
        interaction_id=str(entry.get("interaction_id") or entry.get("op") or ""),
        dataset=str(entry.get("event_dataset") or ""),
        source=str(entry.get("log_source") or entry.get("source") or ""),
        payload=entry.get("payload"),
    )


def normalize_workspace_log_chip(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in WORKSPACE_LOG_CHIP_KEYS else None


def workspace_log_row_matches_chip(row: WorkspaceLogRow, chip: str) -> bool:
    if chip == "all":
        return True
    if chip == "error":
        return row.severity == "ERROR" or row.outcome == "failure"
    return row.category == chip


def filter_workspace_log_rows(
    rows: Sequence[WorkspaceLogRow], *, chip: str, chat_filter: str = ""
) -> list[WorkspaceLogRow]:
    wanted_chat = chat_filter.strip().lower()
    return [
        row
        for row in rows
        if workspace_log_row_matches_chip(row, chip)
        and (not wanted_chat or wanted_chat in row.chat_id.lower())
    ]


def format_workspace_log_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return clip_text(text, 19)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def format_workspace_log_details(row: WorkspaceLogRow) -> str:
    payload = row.payload
    if isinstance(payload, (dict, list)):
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    elif payload is None:
        payload_text = "(empty)"
    else:
        payload_text = str(payload)
    duration = f"{row.duration_ms:.3f} ms" if row.duration_ms is not None else "—"
    return "\n".join(
        [
            f"Time: {row.timestamp or '—'}",
            f"Severity: {row.severity}",
            f"Category: {row.category}",
            f"Action: {row.action or '—'}",
            f"Outcome: {row.outcome}",
            f"Phase: {row.phase or '—'}",
            f"Duration: {duration}",
            f"Chat: {row.chat_id or '—'}",
            f"Interaction: {row.interaction_id or '—'}",
            f"Dataset: {row.dataset or '—'}",
            f"Source: {row.source or '—'}",
            "",
            "Payload:",
            payload_text,
        ]
    )


def parse_sse_lines(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Parse UTF-8-decoded SSE lines into JSON event envelopes."""
    event_id = ""
    event_name = "message"
    data_lines: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if data_lines:
                data_text = "\n".join(data_lines)
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    data = data_text
                yield {"id": event_id, "event": event_name, "data": data}
            event_id = ""
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "id":
            event_id = value
        elif field == "event":
            event_name = value or "message"
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        data_text = "\n".join(data_lines)
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            data = data_text
        yield {"id": event_id, "event": event_name, "data": data}


def make_workspace_log_stream_reader(
    ctx: CLIContext, *, replay: int = WORKSPACE_LOG_REPLAY
) -> WorkspaceLogStreamReader:
    """Create a reconnectable SSE reader using the same auth as the CLI."""
    values = getattr(ctx, "values", {}) or {}
    connect_host = str(values.get("MCP_CONNECT_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    if connect_host in {"0.0.0.0", "::"}:  # nosec B104
        connect_host = "127.0.0.1"
    port = str(values.get("MCP_PORT", "18427")).strip() or "18427"
    base_url = str(getattr(ctx, "base_url", "") or "").rstrip("/") or f"http://{connect_host}:{port}"
    token = str(getattr(ctx, "token", "") or "")
    timeout = float(getattr(ctx, "request_timeout", 15.0) or 15.0)

    def reader(last_event_id: str | None = None) -> Iterator[dict[str, Any]]:
        import httpx

        headers = {"Accept": "text/event-stream", "User-Agent": "bqa-desktop/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        url = f"{base_url}{WORKSPACE_LOG_STREAM_PATH}"
        stream_timeout = httpx.Timeout(timeout, read=30.0)
        with httpx.stream(
            "GET",
            url,
            params={"replay": max(0, min(int(replay), 200))},
            headers=headers,
            timeout=stream_timeout,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            yield from parse_sse_lines(iter(response.iter_lines()))

    return reader


def desktop_ui_pid_path(repo_root: Path) -> Path:
    """Return the pid file used to track detached desktop windows."""
    return Path(repo_root) / "logs" / DESKTOP_UI_PID_FILENAME


def live_desktop_ui_pid(repo_root: Path) -> int | None:
    """Return the pid of a live detached desktop window, if any."""
    pid = read_pid(desktop_ui_pid_path(repo_root))
    if pid is None or pid == os.getpid():
        return None
    parts = process_command_line(pid).split()
    if "app.cli.main" in parts and "ui" in parts:
        return pid
    return None


def register_desktop_ui_pid(repo_root: Path, pid: int) -> None:
    """Record ``pid`` as the detached desktop window instance."""
    path = desktop_ui_pid_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def release_desktop_ui_pid(repo_root: Path, pid: int) -> None:
    """Remove the pid file when it still belongs to ``pid``."""
    path = desktop_ui_pid_path(repo_root)
    if read_pid(path) != pid:
        return
    try:
        path.unlink()
    except OSError:
        pass


def graphical_session_available(environ: dict[str, str] | None = None) -> bool:
    """Return whether the current host advertises a graphical desktop session."""
    values = environ if environ is not None else os.environ
    if sys.platform in {"win32", "darwin"}:
        return True
    return bool(values.get("DISPLAY") or values.get("WAYLAND_DISPLAY"))


def launch_desktop_ui_detached(ctx: CLIContext) -> int:
    """Start the desktop UI independently from the invoking terminal session."""
    existing = live_desktop_ui_pid(ctx.repo_root)
    if existing is not None:
        raise DesktopUIAlreadyRunning(existing)
    log_dir = ctx.repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "desktop-ui.log"
    command = [sys.executable, "-m", "app.cli.main", "ui"]
    child_env = dict(os.environ)
    child_env[BQA_UI_DAEMON_ENV] = "1"
    try:
        with log_path.open("ab", buffering=0) as log_file:
            process = subprocess.Popen(  # nosec B603 - fixed local CLI invocation
                command,
                cwd=ctx.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                env=child_env,
            )
    except OSError as exc:
        raise DesktopUILaunchError(
            f"Không thể khởi động BQA Control Center nền: {exc}"
        ) from exc
    register_desktop_ui_pid(ctx.repo_root, process.pid)
    return process.pid


def _runtime_summary(data: dict[str, Any]) -> tuple[str, str, str]:
    if data.get("ok"):
        return "Sẵn sàng", "#147a45", "MCP bridge và Cloudflare tunnel đang hoạt động."
    if data.get("server", {}).get("running") or data.get("tunnel", {}).get("running"):
        return "Cần kiểm tra", "#a16207", "Một hoặc nhiều thành phần chưa sẵn sàng."
    return "Đã dừng", "#64748b", "Service chưa được khởi động."


class _DesktopDashboard:
    """Tkinter implementation kept private so importing the CLI remains lightweight."""

    def __init__(
        self,
        root: Any,
        tk: Any,
        ttk: Any,
        ctx: CLIContext,
        *,
        initial_message: tuple[str, str] | None,
        status_reader: StatusReader,
        start_action: LifecycleAction,
        restart_action: LifecycleAction,
        activity_reader: ActivityReader,
        stream_reader: StreamJobsReader | None = None,
        workspace_log_stream_reader: WorkspaceLogStreamReader | None = None,
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.ctx = ctx
        self.status_reader = status_reader
        self.start_action = start_action
        self.restart_action = restart_action
        self.activity_reader = activity_reader
        self.stream_reader = stream_reader or make_stream_jobs_reader(ctx)
        self.workspace_log_stream_reader = (
            workspace_log_stream_reader or make_workspace_log_stream_reader(ctx)
        )
        self.workspace_log_stop = threading.Event()
        self.workspace_log_thread: threading.Thread | None = None
        self.workspace_log_chip = WORKSPACE_LOG_DEFAULT_CHIP
        self.workspace_log_rows_all: list[WorkspaceLogRow] = []
        self.workspace_log_rows_by_iid: dict[str, WorkspaceLogRow] = {}
        self.workspace_log_iids: list[str] = []
        self.workspace_log_selected_id: str | None = None
        self.workspace_log_last_event_id: str | None = None
        self.workspace_log_connection_status = "connecting"
        self.workspace_log_connection_error = ""
        self.workspace_log_tree: Any = None
        self.workspace_log_detail: Any = None
        self.workspace_log_notice_var: Any = None
        self.workspace_log_chat_filter_var: Any = None
        self.workspace_log_chip_buttons: dict[str, Any] = {}
        self.busy = False
        self.closed = False
        self.refresh_job: Any = None
        self.workspace_selection_dirty = False
        self.latest_status_data: dict[str, Any] | None = None
        self.action_started_at: float | None = None
        self.action_start_fingerprint: str | None = None
        self.last_toast_fingerprint: str | None = None
        self.active_toast: Any = None
        self.stream_chip = STREAM_DEFAULT_CHIP
        self.stream_rows_all: list[StreamRow] = []
        self.stream_rows_by_iid: dict[str, StreamRow] = {}
        self.stream_iids: list[str] = []
        self.stream_error_message = ""
        self.stream_selected_job_id: str | None = None
        self.stream_inflight = False
        self.stream_tree: Any = None
        self.stream_detail: Any = None
        self.stream_notice_label: Any = None
        self.stream_notice_var: Any = None
        self.stream_chip_buttons: dict[str, Any] = {}
        self.values = {key: tk.StringVar(value="—") for key in (
            "bridge",
            "server",
            "tunnel",
            "endpoint",
            "authentication",
        )}
        self.workspace_var = tk.StringVar(
            value=ctx.values.get("HOST_WORKSPACE_DIR", "")
        )
        self.status_var = tk.StringVar(value="Đang tải")
        self.backend_var = tk.StringVar(value="backend: …")
        self.message_var = tk.StringVar(value=(initial_message or ("", ""))[1])
        self.status_label: Any = None
        self.backend_label: Any = None
        self.action_buttons: list[Any] = []
        self.activity_records: list[dict[str, Any]] = []
        self.activity_tree: Any = None
        self.activity_detail: Any = None
        self._build(initial_message)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self._start_workspace_log_stream()

    def _build(self, initial_message: tuple[str, str] | None) -> None:
        self.root.title("BQA Control Center")
        self.root.geometry("900x690")
        self.root.minsize(720, 560)
        self.root.configure(background="#f5f7fb")

        style = self.ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self.tk.TclError:
            pass
        style.configure("Header.TLabel", font=("TkDefaultFont", 18, "bold"), foreground="#0f172a")
        style.configure("Subtle.TLabel", foreground="#475569")
        style.configure("FieldName.TLabel", foreground="#64748b", font=("TkDefaultFont", 9, "bold"))
        style.configure("Status.TLabel", font=("TkDefaultFont", 11, "bold"), padding=(10, 5))
        style.configure("Chip.TButton", padding=(10, 3))
        style.configure(
            "ChipActive.TButton",
            padding=(10, 3),
            foreground="#ffffff",
            background="#1d4ed8",
        )
        style.map(
            "ChipActive.TButton",
            background=[("active", "#1d4ed8"), ("pressed", "#1e40af")],
            foreground=[("active", "#ffffff")],
        )

        container = self.ttk.Frame(self.root, padding=22)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        header = self.ttk.Frame(container)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.ttk.Label(header, text="BQA Control Center", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.ttk.Label(
            header,
            text="BotQuangAnh Host MCP · local control plane",
            style="Subtle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.status_label = self.ttk.Label(header, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e")
        self.backend_label = self.ttk.Label(
            header, textvariable=self.backend_var, style="Subtle.TLabel"
        )
        self.backend_label.grid(row=0, column=2, rowspan=2, sticky="e", padx=(14, 0))

        summary = self.ttk.Label(container, textvariable=self.message_var, style="Subtle.TLabel", wraplength=820)
        summary.grid(row=1, column=0, sticky="ew", pady=(18, 12))

        notebook = self.ttk.Notebook(container)
        notebook.grid(row=2, column=0, sticky="nsew")
        runtime_tab = self.ttk.Frame(notebook, padding=14)
        stream_tab = self.ttk.Frame(notebook, padding=14)
        workspace_logs_tab = self.ttk.Frame(notebook, padding=14)
        activity_tab = self.ttk.Frame(notebook, padding=14)
        notebook.add(runtime_tab, text="Runtime")
        notebook.add(stream_tab, text="Luồng công việc")
        notebook.add(workspace_logs_tab, text="Workspace Logs")
        notebook.add(activity_tab, text="Hoạt động ChatGPT")

        fields = self.ttk.LabelFrame(runtime_tab, text="Trạng thái runtime", padding=14)
        fields.pack(fill="both", expand=True)
        fields.columnconfigure(1, weight=1)
        rows = [
            ("MCP bridge", "bridge"),
            ("Server", "server"),
            ("Cloudflare tunnel", "tunnel"),
            ("Endpoint", "endpoint"),
            ("Authentication", "authentication"),
            ("Workspace", "workspace"),
        ]
        for index, (label, key) in enumerate(rows):
            self.ttk.Label(fields, text=label, style="FieldName.TLabel").grid(
                row=index, column=0, sticky="nw", padx=(0, 18), pady=5
            )
            if key == "workspace":
                value = self.ttk.Entry(
                    fields,
                    textvariable=self.workspace_var,
                    state="readonly",
                    width=58,
                )
            else:
                value = self.ttk.Label(fields, textvariable=self.values[key], wraplength=500)
            value.grid(row=index, column=1, sticky="ew" if key == "workspace" else "w", pady=5)
            if key == "endpoint":
                copy = self.ttk.Button(fields, text="Copy", command=self.copy_endpoint)
                copy.grid(row=index, column=2, sticky="e", padx=(10, 0), pady=5)
            if key == "workspace":
                browse = self.ttk.Button(fields, text="Chọn thư mục…", command=self.choose_workspace)
                browse.grid(row=index, column=2, sticky="e", padx=(10, 0), pady=5)

        self._build_stream_tab(stream_tab)
        self._build_workspace_logs_tab(workspace_logs_tab)
        self._build_activity_tab(activity_tab)

        actions = self.ttk.Frame(container)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(3, weight=1)
        self._add_action(actions, "Start / Adopt", self.start_service, 0)
        self._add_action(actions, "Restart bridge", self.restart_bridge, 1)
        self._add_action(actions, "Áp dụng workspace", self.apply_workspace, 2)
        self._add_action(actions, "Refresh", self.refresh, 3)
        self.ttk.Button(actions, text="Đóng", command=self.close).grid(row=0, column=4, sticky="e")

        if initial_message:
            self._set_message(*initial_message)

    def _build_workspace_logs_tab(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        parent.rowconfigure(3, weight=1)

        toolbar = self.ttk.Frame(parent)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        chips = self.ttk.Frame(toolbar)
        chips.grid(row=0, column=0, sticky="w")
        for label, key in zip(WORKSPACE_LOG_CHIP_LABELS, WORKSPACE_LOG_CHIP_KEYS):
            button = self.ttk.Button(
                chips,
                text=label,
                style="Chip.TButton",
                command=lambda key=key: self.select_workspace_log_chip(key),
            )
            button.pack(side="left", padx=(0, 6))
            self.workspace_log_chip_buttons[key] = button

        filter_box = self.ttk.Frame(toolbar)
        filter_box.grid(row=0, column=1, sticky="e")
        self.ttk.Label(filter_box, text="Chat filter", style="FieldName.TLabel").pack(
            side="left", padx=(10, 6)
        )
        self.workspace_log_chat_filter_var = self.tk.StringVar(value="")
        chat_entry = self.ttk.Entry(
            filter_box,
            textvariable=self.workspace_log_chat_filter_var,
            width=28,
        )
        chat_entry.pack(side="left")
        chat_entry.bind("<KeyRelease>", lambda _event: self.render_workspace_logs())

        self.workspace_log_notice_var = self.tk.StringVar(value="connecting…")
        self.ttk.Label(
            parent,
            textvariable=self.workspace_log_notice_var,
            style="Subtle.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 5))

        columns = ("time", "severity", "category", "action", "outcome", "duration", "chat")
        tree = self.ttk.Treeview(parent, columns=columns, show="headings", height=9)
        for key, title, width in (
            ("time", "Thời gian (UTC)", 145),
            ("severity", "Severity", 75),
            ("category", "Category", 82),
            ("action", "Action", 170),
            ("outcome", "Outcome", 80),
            ("duration", "ms", 70),
            ("chat", "Chat ID", 170),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key in {"action", "chat"})
        scrollbar = self.ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self.show_selected_workspace_log)
        tree.bind("<Up>", lambda _event: self.move_workspace_log_selection(-1) or "break")
        tree.bind("<Down>", lambda _event: self.move_workspace_log_selection(1) or "break")
        self.workspace_log_tree = tree

        holder = self.ttk.Frame(parent)
        holder.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        holder.columnconfigure(0, weight=1)
        detail = self.tk.Text(holder, height=9, wrap="word", state="disabled")
        detail.grid(row=0, column=0, sticky="nsew")
        self.ttk.Button(holder, text="Copy", command=self.copy_workspace_log_details).grid(
            row=0, column=1, sticky="n", padx=(10, 0)
        )
        self.workspace_log_detail = detail
        self._restyle_workspace_log_chips()
        self.render_workspace_logs()

    def select_workspace_log_chip(self, key: str) -> None:
        normalized = normalize_workspace_log_chip(key)
        if normalized is None or normalized == self.workspace_log_chip:
            return
        self.workspace_log_chip = normalized
        self._restyle_workspace_log_chips()
        self.render_workspace_logs()

    def _restyle_workspace_log_chips(self) -> None:
        for key, button in self.workspace_log_chip_buttons.items():
            active = key == self.workspace_log_chip
            button.configure(style="ChipActive.TButton" if active else "Chip.TButton")

    def _workspace_log_notice(self, visible_count: int) -> str:
        cached = len(self.workspace_log_rows_all)
        if self.workspace_log_connection_status == "live":
            prefix = "LIVE"
        elif self.workspace_log_connection_status == "reconnecting":
            prefix = "RECONNECTING"
        elif self.workspace_log_connection_status == "reset":
            prefix = "RESET"
        else:
            prefix = "CONNECTING"
        error_suffix = (
            f" · {self.workspace_log_connection_error}"
            if self.workspace_log_connection_error
            else ""
        )
        if visible_count:
            return f"{prefix} · {visible_count} visible · {cached} cached{error_suffix}"
        return f"{prefix} · {WORKSPACE_LOG_EMPTY_MESSAGE} · {cached} cached{error_suffix}"

    def render_workspace_logs(self) -> None:
        if self.workspace_log_tree is None or self.workspace_log_notice_var is None:
            return
        chat_filter = (
            self.workspace_log_chat_filter_var.get()
            if self.workspace_log_chat_filter_var is not None
            else ""
        )
        display = filter_workspace_log_rows(
            self.workspace_log_rows_all,
            chip=self.workspace_log_chip,
            chat_filter=chat_filter,
        )
        display = list(reversed(display[-200:]))
        self.workspace_log_notice_var.set(self._workspace_log_notice(len(display)))
        for item in self.workspace_log_tree.get_children():
            self.workspace_log_tree.delete(item)
        self.workspace_log_rows_by_iid = {}
        self.workspace_log_iids = []
        seen: set[str] = set()
        for index, row in enumerate(display):
            fallback = f"{row.interaction_id}:{row.phase}:{row.timestamp}".strip(":")
            base = row.event_id or fallback or f"row-{index}"
            iid = base
            suffix = 2
            while iid in seen:
                iid = f"{base}#{suffix}"
                suffix += 1
            seen.add(iid)
            duration = f"{row.duration_ms:.3f}" if row.duration_ms is not None else "—"
            self.workspace_log_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    format_workspace_log_time(row.timestamp),
                    row.severity,
                    row.category,
                    clip_text(row.action, 42),
                    row.outcome,
                    duration,
                    clip_text(row.chat_id, 36),
                ),
            )
            self.workspace_log_rows_by_iid[iid] = row
            self.workspace_log_iids.append(iid)
        target = None
        if self.workspace_log_selected_id:
            target = next(
                (
                    iid
                    for iid, row in self.workspace_log_rows_by_iid.items()
                    if row.event_id == self.workspace_log_selected_id
                ),
                None,
            )
        if target is None and self.workspace_log_iids:
            target = self.workspace_log_iids[0]
        if target is not None:
            self.workspace_log_tree.selection_set(target)
            self.workspace_log_tree.see(target)
            self.show_selected_workspace_log()
        else:
            self.workspace_log_selected_id = None
            self._set_workspace_log_detail("")

    def _accept_workspace_log_event(self, envelope: dict[str, Any]) -> None:
        if self.closed:
            return
        event_id = str(envelope.get("id") or "")
        row = workspace_log_row_from_mapping(envelope.get("data"), event_id=event_id)
        if row is None:
            return
        if event_id:
            self.workspace_log_last_event_id = event_id
        if row.event_id:
            self.workspace_log_rows_all = [
                item for item in self.workspace_log_rows_all if item.event_id != row.event_id
            ]
        self.workspace_log_rows_all.append(row)
        self.workspace_log_rows_all = self.workspace_log_rows_all[-WORKSPACE_LOG_CACHE_LIMIT:]
        self.workspace_log_connection_status = "live"
        self.workspace_log_connection_error = ""
        self.render_workspace_logs()

    def _accept_workspace_log_control(self, envelope: dict[str, Any]) -> None:
        if self.closed or envelope.get("event") != "stream_reset":
            return
        # The server could not honor Last-Event-ID (rotation, retention, or a
        # bounded snapshot window). Drop the stale cursor and cached timeline
        # so replayed rows are never presented as a gap-free continuation.
        self.workspace_log_last_event_id = None
        self.workspace_log_selected_id = None
        self.workspace_log_rows_all = []
        self.workspace_log_connection_status = "reset"
        self.render_workspace_logs()

    def _set_workspace_log_connection(self, state: str, error: str = "") -> None:
        if self.closed:
            return
        self.workspace_log_connection_status = state
        self.workspace_log_connection_error = clip_text(error, 160) if error else ""
        self.render_workspace_logs()

    def _start_workspace_log_stream(self) -> None:
        if self.workspace_log_thread is not None or self.workspace_log_stream_reader is None:
            return
        reader = self.workspace_log_stream_reader

        def worker() -> None:
            while not self.workspace_log_stop.is_set():
                try:
                    if not self.closed:
                        self.root.after(0, lambda: self._set_workspace_log_connection("connecting"))
                    for envelope in reader(self.workspace_log_last_event_id):
                        if self.workspace_log_stop.is_set() or self.closed:
                            return
                        event_name = envelope.get("event")
                        if event_name == "stream_reset":
                            self.root.after(
                                0,
                                lambda envelope=envelope: self._accept_workspace_log_control(envelope),
                            )
                            continue
                        if event_name != "workspace_log":
                            continue
                        self.root.after(
                            0,
                            lambda envelope=envelope: self._accept_workspace_log_event(envelope),
                        )
                    if self.workspace_log_stop.is_set() or self.closed:
                        return
                    self.root.after(0, lambda: self._set_workspace_log_connection("reconnecting"))
                except Exception as exc:
                    if self.workspace_log_stop.is_set() or self.closed:
                        return
                    message = f"{type(exc).__name__}: {exc}"
                    self.root.after(
                        0,
                        lambda message=message: self._set_workspace_log_connection(
                            "reconnecting", message
                        ),
                    )
                if self.workspace_log_stop.wait(WORKSPACE_LOG_RECONNECT_SECONDS):
                    return

        self.workspace_log_thread = threading.Thread(
            target=worker,
            name="bqa-desktop-workspace-logs",
            daemon=True,
        )
        self.workspace_log_thread.start()

    def show_selected_workspace_log(self, _event: Any = None) -> None:
        if self.workspace_log_tree is None:
            return
        selected = self.workspace_log_tree.selection()
        if not selected:
            return
        row = self.workspace_log_rows_by_iid.get(selected[0])
        if row is None:
            return
        self.workspace_log_selected_id = row.event_id or None
        self._set_workspace_log_detail(format_workspace_log_details(row))

    def move_workspace_log_selection(self, delta: int) -> None:
        if self.workspace_log_tree is None or not self.workspace_log_iids:
            return
        current = (self.workspace_log_tree.selection() or [None])[0]
        target = shifted_selection(self.workspace_log_iids, current, delta)
        if target is not None and target != current:
            self.workspace_log_tree.selection_set(target)
            self.workspace_log_tree.see(target)

    def _set_workspace_log_detail(self, text: str) -> None:
        if self.workspace_log_detail is None:
            return
        self.workspace_log_detail.configure(state="normal")
        self.workspace_log_detail.delete("1.0", "end")
        self.workspace_log_detail.insert("1.0", text)
        self.workspace_log_detail.configure(state="disabled")

    def copy_workspace_log_details(self) -> None:
        if self.workspace_log_tree is None:
            return
        selected = self.workspace_log_tree.selection()
        row = self.workspace_log_rows_by_iid.get(selected[0]) if selected else None
        if row is None:
            self._set_message("warn", "Chưa chọn workspace log nào để copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(format_workspace_log_details(row))
        self.root.update_idletasks()
        self._set_message("success", "Đã copy workspace log vào clipboard.")

    def _build_activity_tab(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=1)
        self.ttk.Label(
            parent,
            text=(
                "Các lệnh host_run_command được gọi qua MCP (ví dụ từ ChatGPT web). "
                "Journal cục bộ, output được giới hạn và redact."
            ),
            style="Subtle.TLabel",
            wraplength=790,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.ttk.Button(parent, text="Refresh activity", command=self.refresh_activity).grid(
            row=0, column=1, sticky="e", pady=(0, 8)
        )

        columns = ("time", "command", "exit", "duration")
        tree = self.ttk.Treeview(parent, columns=columns, show="headings", height=8)
        for key, title, width in (
            ("time", "Thời gian (UTC)", 165),
            ("command", "Command", 410),
            ("exit", "Exit", 60),
            ("duration", "Thời gian", 90),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key == "command")
        scrollbar = self.ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self.show_selected_activity)
        self.activity_tree = tree

        detail = self.tk.Text(parent, height=12, wrap="word", state="disabled")
        detail.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        self.activity_detail = detail

    def _build_stream_tab(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        parent.rowconfigure(3, weight=1)

        chips = self.ttk.Frame(parent)
        chips.grid(row=0, column=0, sticky="w")
        for label, key in zip(STREAM_CHIP_LABELS, STREAM_CHIP_KEYS):
            button = self.ttk.Button(
                chips,
                text=label,
                style="Chip.TButton",
                command=lambda key=key: self.select_stream_chip(key),
            )
            button.pack(side="left", padx=(0, 6))
            self.stream_chip_buttons[key] = button

        self.stream_notice_var = self.tk.StringVar(value="")
        notice = self.ttk.Label(parent, textvariable=self.stream_notice_var, style="Subtle.TLabel")
        notice.grid(row=1, column=0, sticky="w", pady=(6, 2))
        self.stream_notice_label = notice

        columns = ("time", "op", "status", "chat", "detail")
        tree = self.ttk.Treeview(parent, columns=columns, show="headings", height=9)
        for key, title, width in (
            ("time", "Thời gian (UTC)", 150),
            ("op", "Op", 120),
            ("status", "Trạng thái", 95),
            ("chat", "Chat ID", 110),
            ("detail", "Chi tiết", 320),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key == "detail")
        scrollbar = self.ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self.show_selected_stream)
        tree.bind("<Up>", lambda _event: self.move_stream_selection(-1) or "break")
        tree.bind("<Down>", lambda _event: self.move_stream_selection(1) or "break")
        self.stream_tree = tree

        holder = self.ttk.Frame(parent)
        holder.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        holder.columnconfigure(0, weight=1)
        detail = self.tk.Text(holder, height=8, wrap="word", state="disabled")
        detail.grid(row=0, column=0, sticky="nsew")
        self.ttk.Button(holder, text="Copy", command=self.copy_stream_details).grid(
            row=0, column=1, sticky="n", padx=(10, 0)
        )
        self.stream_detail = detail
        self._restyle_stream_chips()
        self.render_stream()

    def select_stream_chip(self, key: str) -> None:
        normalized = normalize_stream_chip(key)
        # Unknown chips are ignored so a stale click can never blank the view.
        if normalized is None or normalized == self.stream_chip:
            return
        self.stream_chip = normalized
        self._restyle_stream_chips()
        self.render_stream()

    def _restyle_stream_chips(self) -> None:
        for key, button in self.stream_chip_buttons.items():
            active = key == self.stream_chip
            button.configure(style="ChipActive.TButton" if active else "Chip.TButton")

    def render_stream(self) -> None:
        """Repaint the stream panel from cached rows; filtering stays local."""
        if self.stream_tree is None or self.stream_notice_var is None:
            return
        display, notice_text = reduce_stream_view(
            self.stream_rows_all,
            chip=self.stream_chip,
            error_message=self.stream_error_message,
        )
        self.stream_notice_var.set(notice_text)
        if notice_text:
            self.stream_notice_label.grid()
        else:
            self.stream_notice_label.grid_remove()
        for item in self.stream_tree.get_children():
            self.stream_tree.delete(item)
        self.stream_rows_by_iid = {}
        self.stream_iids = []
        seen: set[str] = set()
        for index, row in enumerate(display):
            base = row.job_id or f"row-{index}"
            iid = base
            suffix = 2
            while iid in seen:
                iid = f"{base}#{suffix}"
                suffix += 1
            seen.add(iid)
            glyph = stream_status_glyph(row.status)
            values = (
                format_stream_time(row.created_at),
                clip_text(row.op, 40),
                f"{glyph} {row.status}".strip(),
                row.chat_id,
                clip_text(row.detail, 80),
            )
            self.stream_tree.insert("", "end", iid=iid, values=values)
            self.stream_rows_by_iid[iid] = row
            self.stream_iids.append(iid)
        target: str | None = None
        if self.stream_selected_job_id:
            target = next(
                (
                    iid
                    for iid, row in self.stream_rows_by_iid.items()
                    if row.job_id == self.stream_selected_job_id
                ),
                None,
            )
        if target is None and self.stream_iids:
            target = self.stream_iids[0]
        if target is not None:
            self.stream_tree.selection_set(target)
            self.stream_tree.see(target)
            self.show_selected_stream()
        else:
            self.stream_selected_job_id = None
            self._set_stream_detail("")

    def show_selected_stream(self, _event: Any = None) -> None:
        if self.stream_tree is None:
            return
        selected = self.stream_tree.selection()
        if not selected:
            return
        row = self.stream_rows_by_iid.get(selected[0])
        if row is None:
            return
        self.stream_selected_job_id = row.job_id or None
        self._set_stream_detail(format_stream_details(row))

    def move_stream_selection(self, delta: int) -> None:
        if self.stream_tree is None or not self.stream_iids:
            return None
        current = (self.stream_tree.selection() or [None])[0]
        target = shifted_selection(self.stream_iids, current, delta)
        if target is not None and target != current:
            self.stream_tree.selection_set(target)
            self.stream_tree.see(target)
        return None

    def copy_stream_details(self) -> None:
        if self.stream_tree is None:
            return
        selected = self.stream_tree.selection()
        row = self.stream_rows_by_iid.get(selected[0]) if selected else None
        if row is None:
            self._set_message("warn", "Chưa chọn job nào để copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(stream_copy_line(row))
        self.root.update_idletasks()
        self._set_message("success", "Đã copy thông tin job vào clipboard.")

    def _set_stream_detail(self, text: str) -> None:
        if self.stream_detail is None:
            return
        self.stream_detail.configure(state="normal")
        self.stream_detail.delete("1.0", "end")
        self.stream_detail.insert("1.0", text)
        self.stream_detail.configure(state="disabled")

    def refresh_stream(self) -> None:
        """Fetch jobs off the UI thread; results land via ``root.after``."""
        if self.closed or self.stream_inflight or self.stream_reader is None:
            return
        reader = self.stream_reader
        self.stream_inflight = True

        def worker() -> None:
            error: BaseException | None = None
            payload: Any = None
            try:
                payload = reader()
            except Exception as exc:  # REST failures must degrade to the muted line.
                error = exc
            rows = [] if error is not None else stream_rows_from_payload(payload)
            if self.closed:
                return
            self.root.after(0, lambda: self._finish_stream_fetch(rows, error))

        threading.Thread(target=worker, name="bqa-desktop-stream", daemon=True).start()

    def _finish_stream_fetch(self, rows: list[StreamRow], error: BaseException | None) -> None:
        self.stream_inflight = False
        if self.closed:
            return
        self.stream_rows_all = rows
        self.stream_error_message = stream_error_message(error) if error is not None else ""
        self.render_stream()

    def _add_action(self, parent: Any, text: str, command: Callable[[], None], column: int) -> None:
        button = self.ttk.Button(parent, text=text, command=command)
        button.grid(row=0, column=column, sticky="w", padx=(0, 8))
        self.action_buttons.append(button)

    def _set_message(self, kind: str, text: str) -> None:
        colors = {"success": "#147a45", "warn": "#a16207", "error": "#b91c1c"}
        self.message_var.set(text)
        self.status_label.configure(foreground=colors.get(kind, "#475569"))

    def refresh(self) -> None:
        if self.closed:
            return
        self.refresh_job = None
        try:
            data = self.status_reader(self.ctx.repo_root, self.ctx.values)
            state, color, summary = _runtime_summary(data)
            self.latest_status_data = data
            self.status_var.set(state)
            self.status_label.configure(foreground=color)
            badge_text, badge_color = backend_badge(data)
            self.backend_var.set(badge_text)
            if self.backend_label is not None:
                self.backend_label.configure(foreground=badge_color)
            if not self.busy:
                self.message_var.set(summary)
            self.values["bridge"].set(str(data.get("bridge", "unknown")))
            self.values["server"].set("running" if data.get("server", {}).get("running") else "stopped")
            self.values["tunnel"].set("running" if data.get("tunnel", {}).get("running") else "stopped")
            self.values["endpoint"].set(data.get("url") or data.get("last_known_url") or "chưa có")
            self.values["authentication"].set("enabled" if data.get("auth_required") else "disabled")
            if not self.workspace_selection_dirty:
                self.workspace_var.set(data.get("workspace", self.workspace_var.get()))
        except Exception as exc:
            self.status_var.set("Lỗi trạng thái")
            self.status_label.configure(foreground="#b91c1c")
            self.backend_var.set(BACKEND_DOWN_BADGE[0])
            if self.backend_label is not None:
                self.backend_label.configure(foreground=BACKEND_DOWN_BADGE[1])
            self.message_var.set(f"Không đọc được trạng thái runtime: {exc}")
        finally:
            if not self.closed:
                self._schedule_refresh()
        self.refresh_activity()
        self.refresh_stream()

    def refresh_activity(self) -> None:
        if self.closed or self.activity_tree is None:
            return
        try:
            records = self.activity_reader(20)
        except Exception as exc:
            self._set_activity_detail(f"Không đọc được lịch sử MCP: {exc}")
            return
        fingerprint = [str(record.get("event_id", "")) for record in records]
        current = list(self.activity_tree.get_children())
        if fingerprint == current:
            return
        for item in current:
            self.activity_tree.delete(item)
        self.activity_records = records
        for index, record in enumerate(records):
            event_id = str(record.get("event_id") or index)
            timestamp = str(record.get("timestamp", "")).replace("T", " ").replace("+00:00", "Z")
            command = self._short_activity_text(record.get("command", ""), 90)
            exit_code = "timeout" if record.get("timed_out") else str(record.get("exit_code", "—"))
            duration = record.get("duration_ms")
            duration_text = f"{duration} ms" if duration is not None else "—"
            self.activity_tree.insert("", "end", iid=event_id, values=(timestamp, command, exit_code, duration_text))
        if records:
            self.activity_tree.selection_set(str(records[0].get("event_id") or 0))
            self.show_selected_activity()
        else:
            self._set_activity_detail("Chưa có lệnh host_run_command nào được ghi nhận qua MCP.")

    @staticmethod
    def _short_activity_text(value: Any, limit: int) -> str:
        return clip_text(value, limit)

    def _set_activity_detail(self, text: str) -> None:
        if self.activity_detail is None:
            return
        self.activity_detail.configure(state="normal")
        self.activity_detail.delete("1.0", "end")
        self.activity_detail.insert("1.0", text)
        self.activity_detail.configure(state="disabled")

    def show_selected_activity(self, _event: Any = None) -> None:
        if self.activity_tree is None:
            return
        selected = self.activity_tree.selection()
        if not selected:
            return
        event_id = selected[0]
        record = next(
            (item for item in self.activity_records if str(item.get("event_id")) == event_id),
            None,
        )
        if record is None:
            return
        lines = [
            f"Time: {record.get('timestamp', '—')}",
            f"CWD: {record.get('cwd', '—')}",
            f"Exit code: {record.get('exit_code', '—')}",
            f"Duration: {record.get('duration_ms', '—')} ms",
            "",
            "$ " + str(record.get("command", "")),
            "",
            "stdout:",
            str(record.get("stdout", "")) or "(empty)",
            "",
            "stderr:",
            str(record.get("stderr", "")) or "(empty)",
        ]
        self._set_activity_detail("\n".join(lines))

    def _schedule_refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(2_000, self.refresh)

    def _run_action(self, label: str, action: Callable[[], dict[str, Any]]) -> None:
        if self.busy:
            return
        self.busy = True
        self.action_started_at = time.monotonic()
        self.action_start_fingerprint = (
            completion_fingerprint(self.latest_status_data)
            if isinstance(self.latest_status_data, dict)
            else None
        )
        self.message_var.set(f"Đang chạy: {label}…")
        for button in self.action_buttons:
            button.state(["disabled"])

        def worker() -> None:
            try:
                result = action()
                if result.get("ok", True):
                    outcome = ("success", str(result.get("message") or f"Hoàn tất: {label}."))
                else:
                    outcome = ("error", str(result.get("message") or f"Không hoàn tất: {label}."))
            except Exception as exc:  # Lifecycle errors should stay inside the GUI.
                outcome = ("error", f"Không thể {label.lower()}: {exc}")
            elapsed = time.monotonic() - (self.action_started_at or time.monotonic())
            if not self.closed:
                self.root.after(0, lambda: self._finish_action(*outcome, elapsed_seconds=elapsed))

        threading.Thread(target=worker, name="bqa-desktop-action", daemon=True).start()

    def _finish_action(self, kind: str, text: str, elapsed_seconds: float = 0.0) -> None:
        if self.closed:
            return
        self.busy = False
        for button in self.action_buttons:
            button.state(["!disabled"])
        self._set_message(kind, text)
        self.refresh()
        self._maybe_show_completion_toast(text, elapsed_seconds)

    def _maybe_show_completion_toast(self, text: str, elapsed_seconds: float) -> None:
        """Fire the one-shot completion toast for long tracked operations."""
        if not isinstance(self.latest_status_data, dict):
            return
        current = completion_fingerprint(self.latest_status_data)
        due = completion_toast_due(
            elapsed_seconds,
            self.action_start_fingerprint,
            current,
            self.last_toast_fingerprint,
        )
        if not due:
            return
        self.last_toast_fingerprint = current
        self.show_completion_toast(
            "Hoàn tất sau " + f"{elapsed_seconds:.0f}s",
            text,
        )

    def show_completion_toast(self, title: str, message: str) -> None:
        """Pop a transient bottom-right notification window."""
        try:
            if self.active_toast is not None:
                self.active_toast.destroy()
        except self.tk.TclError:
            pass
        try:
            toast = self.tk.Toplevel(self.root)
            toast.title("BQA Control Center")
            toast.resizable(False, False)
            toast.configure(bg="#f5f7fb", padx=16, pady=12)
            try:
                toast.attributes("-topmost", True)
            except self.tk.TclError:
                pass
            self.tk.Label(
                toast,
                text=title,
                font=("TkDefaultFont", 10, "bold"),
                fg="#147a45",
                bg="#f5f7fb",
            ).pack(anchor="w")
            self.tk.Label(
                toast,
                text=message,
                wraplength=320,
                justify="left",
                fg="#0f172a",
                bg="#f5f7fb",
            ).pack(anchor="w", pady=(4, 0))
            toast.update_idletasks()
            width = toast.winfo_reqwidth()
            height = toast.winfo_reqheight()
            x = max(0, toast.winfo_screenwidth() - width - 24)
            y = max(0, toast.winfo_screenheight() - height - 56)
            toast.geometry(f"+{x}+{y}")
            toast.after(COMPLETION_TOAST_LIFETIME_MS, toast.destroy)
            self.active_toast = toast
        except self.tk.TclError:
            return

    def start_service(self) -> None:
        self._run_action("start/adopt service", lambda: self.start_action(self.ctx.repo_root))

    def restart_bridge(self) -> None:
        self._run_action(
            "restart MCP bridge (giữ nguyên tunnel)",
            lambda: self.restart_action(self.ctx.repo_root, self.ctx.values),
        )

    def choose_workspace(self) -> None:
        from tkinter import filedialog

        initial = self.workspace_var.get()
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Chọn workspace cho BotQuangAnh Host MCP",
            initialdir=initial if initial else None,
            mustexist=True,
        )
        if selected:
            self.workspace_var.set(selected)
            self.workspace_selection_dirty = True
            self._set_message(
                "warn",
                "Đã chọn workspace mới. Bấm ‘Áp dụng workspace’ để lưu và restart bridge.",
            )

    def apply_workspace(self) -> None:
        selected = self.workspace_var.get()
        self.workspace_selection_dirty = False

        def apply() -> dict[str, Any]:
            updates = set_workspace_config(self.ctx.repo_root, selected)
            self.ctx.values.update(updates)
            result = self.restart_action(self.ctx.repo_root, self.ctx.values)
            return {
                "ok": bool(result.get("ok", True)),
                "message": "Workspace đã được lưu và MCP bridge đã restart; tunnel được giữ nguyên.",
            }

        self._run_action("áp dụng workspace", apply)

    def copy_endpoint(self) -> None:
        endpoint = self.values["endpoint"].get()
        if not endpoint or endpoint == "chưa có":
            self._set_message("warn", "Chưa có endpoint để copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(endpoint)
        self.root.update_idletasks()
        self._set_message("success", "Đã copy endpoint vào clipboard.")

    def close(self) -> None:
        self.closed = True
        self.workspace_log_stop.set()
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.root.destroy()


def run_desktop_ui(
    ctx: CLIContext,
    *,
    initial_message: tuple[str, str] | None = None,
    status_reader: StatusReader = status_data,
    start_action: LifecycleAction = start,
    restart_action: LifecycleAction = restart,
    activity_reader: ActivityReader = read_mcp_command_activity,
    stream_reader: StreamJobsReader | None = None,
    workspace_log_stream_reader: WorkspaceLogStreamReader | None = None,
) -> int:
    """Open the native Tkinter control window and return after it is closed."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:  # pragma: no cover - depends on Python build
        raise DesktopUIUnavailable("Python was built without Tkinter.") from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise DesktopUIUnavailable("No graphical display is available for the BQA window.") from exc

    _DesktopDashboard(
        root,
        tk,
        ttk,
        ctx,
        initial_message=initial_message,
        status_reader=status_reader,
        start_action=start_action,
        restart_action=restart_action,
        activity_reader=activity_reader,
        stream_reader=stream_reader,
        workspace_log_stream_reader=workspace_log_stream_reader,
    )
    root.mainloop()
    return 0
