"""Workspace journal model, SSE reader, and Tkinter log view."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import queue
import threading
from typing import Any

from app.cli.desktop_views.activity import (
    clip_text,
    restore_tree_vertical_scroll_position,
    tree_vertical_scroll_position,
)
from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
from app.cli.desktop_views.activity import ActivityNotification
from app.cli.desktop_views.theme import InspectorTabs


WORKSPACE_LOG_STREAM_PATH = "/api/v1/activity/stream"
WORKSPACE_LOG_REPLAY = 100
WORKSPACE_LOG_CACHE_LIMIT = 500
WORKSPACE_LOG_CHIP_KEYS = ("all", "error", "process", "file", "session")
WORKSPACE_LOG_RECONNECT_SECONDS = 2.0


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


def workspace_log_row_from_mapping(entry: Any, *, event_id: str = "") -> WorkspaceLogRow | None:
    """Convert a loose SSE/journal mapping to a stable desktop row."""
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
    rows: Sequence[WorkspaceLogRow], *, chip: str, chat_filter: str = "", outcome: str = "all"
) -> list[WorkspaceLogRow]:
    wanted_chat = chat_filter.strip().lower()
    wanted_outcome = outcome.strip().lower()
    return [
        row
        for row in rows
        if workspace_log_row_matches_chip(row, chip)
        and (not wanted_chat or wanted_chat in row.chat_id.lower())
        and (wanted_outcome in {"", "all"} or row.outcome == wanted_outcome)
    ]


def format_workspace_log_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return " ".join(text.split())[:19]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def format_workspace_log_details(
    row: WorkspaceLogRow, translator: DesktopTranslator | None = None
) -> str:
    translator = translator or DesktopTranslator()
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
            translator.text("workspace_logs.detail.time", value=row.timestamp or "—"),
            translator.text("workspace_logs.detail.severity", value=row.severity),
            translator.text("workspace_logs.detail.category", value=row.category),
            translator.text("workspace_logs.detail.action", value=row.action or "—"),
            translator.text("workspace_logs.detail.outcome", value=row.outcome),
            translator.text("workspace_logs.detail.phase", value=row.phase or "—"),
            translator.text("workspace_logs.detail.duration", value=duration),
            translator.text("workspace_logs.detail.chat", value=row.chat_id or "—"),
            translator.text("workspace_logs.detail.interaction", value=row.interaction_id or "—"),
            translator.text("workspace_logs.detail.dataset", value=row.dataset or "—"),
            translator.text("workspace_logs.detail.source", value=row.source or "—"),
            "",
            translator.text("workspace_logs.detail.payload"),
            payload_text,
        ]
    )


def workspace_log_inspector_content(
    row: WorkspaceLogRow, translator: DesktopTranslator | None = None
) -> dict[str, str]:
    """Split a journal event into the three panes shown by the inspector."""
    payload = row.payload
    if isinstance(payload, (dict, list)):
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    elif payload is None:
        payload_text = "(empty)"
    else:
        payload_text = str(payload)
    metadata = {
        "event_id": row.event_id or None,
        "timestamp": row.timestamp or None,
        "severity": row.severity,
        "category": row.category,
        "outcome": row.outcome,
        "phase": row.phase or None,
        "duration_ms": row.duration_ms,
        "chat_id": row.chat_id or None,
        "interaction_id": row.interaction_id or None,
        "dataset": row.dataset or None,
        "source": row.source or None,
    }
    return {
        "summary": format_workspace_log_details(row, translator),
        "metadata": json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        "payload": payload_text,
    }


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
            event_id, event_name, data_lines = "", "message", []
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
    ctx: Any, *, replay: int = WORKSPACE_LOG_REPLAY
) -> Callable[[str | None], Iterator[dict[str, Any]]]:
    """Create an authenticated reconnectable SSE reader for the CLI endpoint."""
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
        with httpx.stream(
            "GET",
            f"{base_url}{WORKSPACE_LOG_STREAM_PATH}",
            params={"replay": max(0, min(int(replay), 200))},
            headers=headers,
            timeout=httpx.Timeout(timeout, read=30.0),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            yield from parse_sse_lines(iter(response.iter_lines()))

    return reader


def _shifted_selection(order: Sequence[str], current: str | None, delta: int) -> str | None:
    if not order:
        return None
    index = order.index(current) + delta if current in order else (0 if delta >= 0 else len(order) - 1)
    return order[max(0, min(len(order) - 1, index))]


class WorkspaceLogView:
    """Own the Workspace Logs widgets, cache, SSE lifecycle, and filters."""

    def __init__(
        self,
        *,
        on_new_activity: Callable[[ActivityNotification], None],
        root: Any = None,
        tk: Any = None,
        ttk: Any = None,
        parent: Any = None,
        stream_reader: Callable[[str | None], Iterator[dict[str, Any]]] | None = None,
        on_message: Callable[[str, str], None] | None = None,
        on_status_change: Callable[[str], None] | None = None,
        translator: DesktopTranslator | None = None,
    ) -> None:
        self.on_new_activity = on_new_activity
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.stream_reader = stream_reader
        self.on_message = on_message or (lambda _kind, _message: None)
        self.on_status_change = on_status_change or (lambda _state: None)
        self.translator = translator or DesktopTranslator()
        self.bindings = TranslationBindings(self.translator)
        self.closed = False
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.drain_job: Any = None
        self.chip = "all"
        self.rows: list[WorkspaceLogRow] = []
        self.rows_by_iid: dict[str, WorkspaceLogRow] = {}
        self.iids: list[str] = []
        self.selected_id: str | None = None
        self.seen_event_ids: set[str] = set()
        self.seen_activity_ids: set[str] = set()
        self.suppress_replay_activity_notifications = False
        self.last_event_id: str | None = None
        self.connection_status = "connecting"
        self.connection_error = ""
        self.tree: Any = None
        self.inspector: InspectorTabs | None = None
        self.notice_var: Any = None
        self.chat_filter_var: Any = None
        self.outcome_var: Any = None
        self.chip_buttons: dict[str, Any] = {}
        if parent is not None:
            self._build(parent)

    def set_translator(self, translator: DesktopTranslator) -> None:
        """Relabel the visible log view without dropping its stream cache or selection."""
        self.translator = translator
        self.bindings.set_translator(translator)
        self._apply_tree_labels()
        if self.inspector is not None:
            for key, label_key in (
                ("summary", "workspace_logs.summary"),
                ("metadata", "workspace_logs.metadata"),
                ("payload", "workspace_logs.payload"),
            ):
                self.inspector.set_tab_label(key, translator.text(label_key))
            self.inspector.set_copy_messages(
                empty=translator.text("inspector.copy_empty"),
                success=translator.text("inspector.copy_success"),
                selection_success=translator.text("inspector.copy_selection_success"),
            )
        self.render()

    def _apply_tree_labels(self) -> None:
        if self.tree is None:
            return
        for key, label_key in (
            ("time", "workspace_logs.time"),
            ("severity", "workspace_logs.severity"),
            ("category", "workspace_logs.category"),
            ("action", "workspace_logs.action"),
            ("outcome", "workspace_logs.outcome"),
            ("duration", "activity.milliseconds"),
            ("chat", "workspace_logs.chat_id"),
        ):
            self.tree.heading(key, text=self.translator.text(label_key))

    def _build(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)
        title = self.ttk.Label(parent, style="SectionHeader.TLabel")
        self.bindings.bind(title, "tab.workspace_logs")
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))
        toolbar = self.ttk.Frame(parent)
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        chips = self.ttk.Frame(toolbar)
        chips.grid(row=0, column=0, sticky="w")
        for key in WORKSPACE_LOG_CHIP_KEYS:
            button = self.ttk.Button(
                chips,
                style="Chip.TButton",
                command=lambda key=key: self.select_chip(key),
            )
            self.bindings.bind(button, f"workspace_logs.{key}")
            button.pack(side="left", padx=(0, 6))
            self.chip_buttons[key] = button
        filter_box = self.ttk.Frame(toolbar)
        filter_box.grid(row=0, column=1, sticky="e")
        chat_filter_label = self.ttk.Label(filter_box, style="FieldName.TLabel")
        self.bindings.bind(chat_filter_label, "field.chat_filter")
        chat_filter_label.pack(side="left", padx=(10, 6))
        self.chat_filter_var = self.tk.StringVar(value="")
        chat_entry = self.ttk.Entry(
            filter_box,
            textvariable=self.chat_filter_var,
            width=28,
            style="Filter.TEntry",
        )
        chat_entry.pack(side="left")
        chat_entry.bind("<KeyRelease>", lambda _event: self.render())
        self.outcome_var = self.tk.StringVar(value="all")
        outcome = self.ttk.Combobox(
            filter_box,
            textvariable=self.outcome_var,
            values=("all", "success", "failure", "unknown"),
            state="readonly",
            width=10,
            style="Filter.TCombobox",
        )
        outcome.pack(side="left", padx=(6, 0))
        outcome.bind("<<ComboboxSelected>>", lambda _event: self.render())
        clear = self.ttk.Button(filter_box, command=self.clear_filters)
        self.bindings.bind(clear, "action.clear")
        clear.pack(side="left", padx=(6, 0))
        self.notice_var = self.tk.StringVar(
            value=self.translator.text("workspace_logs.connecting")
        )
        self.ttk.Label(parent, textvariable=self.notice_var, style="Subtle.TLabel").grid(row=2, column=0, sticky="w", pady=(7, 5))
        panes = self.ttk.Panedwindow(parent, orient="vertical")
        panes.grid(row=3, column=0, sticky="nsew")
        table = self.ttk.Frame(panes, style="Surface.TFrame")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("time", "severity", "category", "action", "outcome", "duration", "chat")
        tree = self.ttk.Treeview(table, columns=columns, show="headings", height=9, style="Table.Treeview")
        for key, width in (("time", 145), ("severity", 75), ("category", 82), ("action", 170), ("outcome", 80), ("duration", 70), ("chat", 170)):
            tree.heading(key)
            tree.column(key, width=width, stretch=key in {"action", "chat"})
        scrollbar = self.ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self.show_selected)
        tree.bind("<Up>", lambda _event: self.move_selection(-1) or "break")
        tree.bind("<Down>", lambda _event: self.move_selection(1) or "break")
        self.tree = tree
        self._apply_tree_labels()
        holder = self.ttk.LabelFrame(panes, padding=6, style="InspectorCard.TLabelframe")
        self.bindings.bind(holder, "workspace_logs.inspector")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.inspector = InspectorTabs(
            root=self.root,
            tk=self.tk,
            ttk=self.ttk,
            parent=holder,
            tabs=(
                ("summary", self.translator.text("workspace_logs.summary")),
                ("metadata", self.translator.text("workspace_logs.metadata")),
                ("payload", self.translator.text("workspace_logs.payload")),
            ),
            on_message=self.on_message,
            copy_empty_message=self.translator.text("inspector.copy_empty"),
            copy_success_message=self.translator.text("inspector.copy_success"),
            copy_selection_success_message=self.translator.text("inspector.copy_selection_success"),
        )
        self.inspector.grid(row=0, column=0, sticky="nsew")
        copy_tab = self.ttk.Button(holder, command=self.copy_details)
        self.bindings.bind(copy_tab, "action.copy_tab")
        copy_tab.grid(row=1, column=0, sticky="e", pady=(6, 0))
        panes.add(table, weight=2)
        panes.add(holder, weight=1)
        self._restyle_chips()
        self.render()

    def select_chip(self, key: str) -> None:
        normalized = normalize_workspace_log_chip(key)
        if normalized is None or normalized == self.chip:
            return
        self.chip = normalized
        self._restyle_chips()
        self.render()

    def clear_filters(self) -> None:
        self.chip = "all"
        if self.chat_filter_var is not None:
            self.chat_filter_var.set("")
        if self.outcome_var is not None:
            self.outcome_var.set("all")
        self._restyle_chips()
        self.render()

    def _restyle_chips(self) -> None:
        for key, button in self.chip_buttons.items():
            button.configure(style="ChipActive.TButton" if key == self.chip else "Chip.TButton")

    def _notice(self, visible_count: int) -> str:
        state_key = {
            "live": "workspace_logs.state.live",
            "reconnecting": "workspace_logs.state.reconnecting",
            "reset": "workspace_logs.state.reset",
        }.get(self.connection_status, "workspace_logs.state.connecting")
        prefix = self.translator.text(state_key)
        error_suffix = f" · {self.connection_error}" if self.connection_error else ""
        if visible_count:
            return self.translator.text(
                "workspace_logs.notice",
                state=prefix,
                visible=visible_count,
                cached=len(self.rows),
                error=error_suffix,
            )
        return self.translator.text(
            "workspace_logs.notice_empty",
            state=prefix,
            empty=self.translator.text("workspace_logs.empty"),
            cached=len(self.rows),
            error=error_suffix,
        )

    def render(self) -> None:
        if self.tree is None or self.notice_var is None:
            return
        chat_filter = self.chat_filter_var.get() if self.chat_filter_var is not None else ""
        outcome = self.outcome_var.get() if self.outcome_var is not None else "all"
        display = list(
            reversed(
                filter_workspace_log_rows(
                    self.rows,
                    chip=self.chip,
                    chat_filter=chat_filter,
                    outcome=outcome,
                )[-200:]
            )
        )
        self.notice_var.set(self._notice(len(display)))
        existing_items = self.tree.get_children()
        scroll_position = tree_vertical_scroll_position(self.tree)
        for item in existing_items:
            self.tree.delete(item)
        self.rows_by_iid, self.iids = {}, []
        seen: set[str] = set()
        for index, row in enumerate(display):
            fallback = f"{row.interaction_id}:{row.phase}:{row.timestamp}".strip(":")
            base = row.event_id or fallback or f"row-{index}"
            iid, suffix = base, 2
            while iid in seen:
                iid, suffix = f"{base}#{suffix}", suffix + 1
            seen.add(iid)
            duration = f"{row.duration_ms:.3f}" if row.duration_ms is not None else "—"
            self.tree.insert("", "end", iid=iid, values=(format_workspace_log_time(row.timestamp), row.severity, row.category, clip_text(row.action, 42), row.outcome, duration, clip_text(row.chat_id, 36)))
            self.rows_by_iid[iid] = row
            self.iids.append(iid)
        target = next((iid for iid, row in self.rows_by_iid.items() if row.event_id == self.selected_id), None)
        if target is None and self.iids:
            target = self.iids[0]
        if target is not None:
            self.tree.selection_set(target)
            if not existing_items:
                self.tree.see(target)
            self.show_selected()
        else:
            self.selected_id = None
            self._set_detail({"summary": "", "metadata": "", "payload": ""})
        restore_tree_vertical_scroll_position(self.tree, scroll_position)

    def accept_event(self, envelope: dict[str, Any]) -> None:
        """Accept one decoded SSE envelope and deliver a new chat transition once."""
        if self.closed:
            return
        data = envelope.get("data")
        row = workspace_log_row_from_mapping(data, event_id=str(envelope.get("id") or ""))
        if row is None:
            return
        seen_key = row.event_id or "|".join((row.chat_id, row.interaction_id, row.phase, row.timestamp, row.action))
        is_new = bool(seen_key) and seen_key not in self.seen_event_ids
        if seen_key:
            self.seen_event_ids.add(seen_key)
        notification_id = row.interaction_id or seen_key
        activity_key = f"{row.chat_id}|{notification_id}" if row.chat_id else notification_id
        is_new_activity = bool(activity_key) and activity_key not in self.seen_activity_ids
        if activity_key:
            self.seen_activity_ids.add(activity_key)
        if row.event_id:
            self.last_event_id = row.event_id
            self.rows = [item for item in self.rows if item.event_id != row.event_id]
        self.rows.append(row)
        self.rows = self.rows[-WORKSPACE_LOG_CACHE_LIMIT:]
        self.connection_status, self.connection_error = "live", ""
        self.on_status_change(self.connection_status)
        self.render()
        if is_new and is_new_activity and row.chat_id and not self.suppress_replay_activity_notifications:
            self.on_new_activity(ActivityNotification(row.chat_id, notification_id))

    def accept_control(self, envelope: dict[str, Any]) -> None:
        if self.closed:
            return
        if envelope.get("event") == "stream_replay":
            data = envelope.get("data")
            phase = str(data.get("phase") or "") if isinstance(data, dict) else ""
            if phase == "start":
                self.suppress_replay_activity_notifications = bool(
                    data.get("baseline") if isinstance(data, dict) else False
                )
            elif phase == "complete":
                self.suppress_replay_activity_notifications = False
            return
        if envelope.get("event") != "stream_reset":
            return
        self.last_event_id = None
        self.selected_id = None
        self.rows = []
        self.connection_status, self.connection_error = "reset", ""
        self.on_status_change(self.connection_status)
        self.render()

    def set_connection(self, state: str, error: str = "") -> None:
        if self.closed:
            return
        self.connection_status = state
        self.connection_error = clip_text(error, 160) if error else ""
        self.on_status_change(self.connection_status)
        self.render()

    def start_stream(self) -> None:
        """Start one daemon reader; Tk drains its thread-safe event queue."""
        if self.thread is not None or self.stream_reader is None:
            return

        self._schedule_queue_drain()

        def worker() -> None:
            while not self.stop_event.is_set():
                try:
                    self.event_queue.put(("connection", ("connecting", "")))
                    for envelope in self.stream_reader(self.last_event_id):
                        if self.stop_event.is_set() or self.closed:
                            return
                        if envelope.get("event") == "stream_reset":
                            self.event_queue.put(("control", envelope))
                        elif envelope.get("event") == "workspace_log":
                            self.event_queue.put(("event", envelope))
                    if self.stop_event.is_set() or self.closed:
                        return
                    self.event_queue.put(("connection", ("reconnecting", "")))
                except Exception as exc:
                    if self.stop_event.is_set() or self.closed:
                        return
                    message = f"{type(exc).__name__}: {exc}"
                    self.event_queue.put(("connection", ("reconnecting", message)))
                if self.stop_event.wait(WORKSPACE_LOG_RECONNECT_SECONDS):
                    return

        self.thread = threading.Thread(target=worker, name="bqa-desktop-workspace-logs", daemon=True)
        self.thread.start()

    def _schedule_queue_drain(self) -> None:
        if self.closed or self.root is None:
            return
        self.drain_job = self.root.after(50, self._drain_queue)

    def _drain_queue(self) -> None:
        """Run only on Tk's event loop and apply worker events in arrival order."""
        self.drain_job = None
        while not self.closed:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "event":
                self.accept_event(payload)
            elif kind == "control":
                self.accept_control(payload)
            elif kind == "connection":
                state, error = payload
                self.set_connection(state, error)
        self._schedule_queue_drain()

    def show_selected(self, _event: Any = None) -> None:
        if self.tree is None:
            return
        selected = self.tree.selection()
        row = self.rows_by_iid.get(selected[0]) if selected else None
        if row is None:
            return
        self.selected_id = row.event_id or None
        self._set_detail(workspace_log_inspector_content(row, self.translator))

    def move_selection(self, delta: int) -> None:
        if self.tree is None:
            return
        current = (self.tree.selection() or [None])[0]
        target = _shifted_selection(self.iids, current, delta)
        if target is not None and target != current:
            self.tree.selection_set(target)
            self.tree.see(target)

    def _set_detail(self, contents: dict[str, str]) -> None:
        if self.inspector is None:
            return
        for key, content in contents.items():
            self.inspector.set_content(key, content)

    def copy_details(self) -> None:
        if self.tree is None:
            return
        selected = self.tree.selection()
        row = self.rows_by_iid.get(selected[0]) if selected else None
        if row is None:
            self.on_message("warn", self.translator.text("workspace_logs.select_row"))
            return
        if self.inspector is not None:
            self.inspector.copy_active()

    def close(self) -> None:
        """Stop the worker before the dashboard destroys its root window."""
        self.closed = True
        self.stop_event.set()
        if self.drain_job is not None and self.root is not None:
            try:
                self.root.after_cancel(self.drain_job)
            except Exception:
                pass
            self.drain_job = None
