"""Workplace session and host-command activity view.

The module deliberately keeps the activity data model independent from Tk so
the dashboard can be tested without creating a graphical display.  The
``ActivityView`` widget implementation is added alongside these helpers as
the former dashboard-owned controls are migrated.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
from app.cli.desktop_views.theme import PALETTE, InspectorTabs


CHAT_WORKSPACE_ARCHIVE_DIR = ".archive"
_TERMINAL_ACTIVITY_STATUSES = {"succeeded", "failed", "timed_out"}
_VALID_ACTIVITY_PHASES = {"started", "completed"}
_VALID_ACTIVITY_STATUSES = _TERMINAL_ACTIVITY_STATUSES | {"running"}


@dataclass(frozen=True)
class WorkspaceSession:
    """One active workplace directory represented in the activity rail."""

    chat_id: str
    path: Path
    last_changed: float


@dataclass(frozen=True)
class ActivityNotification:
    """One post-baseline command eligible to reveal and focus a workplace."""

    chat_id: str
    operation_id: str


def discover_workspace_sessions(root: Path) -> list[WorkspaceSession]:
    """List direct workplace folders, newest first, without entering archives."""
    try:
        children = list(root.iterdir())
    except OSError:
        return []
    sessions: list[WorkspaceSession] = []
    for child in children:
        if child.name == CHAT_WORKSPACE_ARCHIVE_DIR or child.name.startswith("."):
            continue
        try:
            if not child.is_dir():
                continue
            last_changed = child.stat().st_mtime
        except OSError:
            continue
        for name in ("journal.jsonl", "meta.json"):
            try:
                last_changed = max(last_changed, (child / name).stat().st_mtime)
            except OSError:
                continue
        sessions.append(
            WorkspaceSession(
                chat_id=child.name,
                path=child,
                last_changed=last_changed,
            )
        )
    return sorted(sessions, key=lambda item: (-item.last_changed, item.chat_id))


def filter_activity_records_for_session(
    records: Sequence[dict[str, Any]], chat_id: str | None
) -> list[dict[str, Any]]:
    """Return every command call, or only the currently selected workplace."""
    if not chat_id:
        return list(records)
    return [record for record in records if str(record.get("chat_id") or "") == chat_id]


def command_activity_status(record: dict[str, Any]) -> str:
    """Return a UI status while retaining support for pre-lifecycle records."""
    status = str(record.get("status") or "")
    if status in _VALID_ACTIVITY_STATUSES:
        return status
    if record.get("timed_out"):
        return "timed_out"
    return "succeeded" if record.get("ok") else "failed"


def activity_status_label(
    status: str, translator: DesktopTranslator | None = None
) -> str:
    """Translate a stable activity status into the compact rail/table label."""
    translator = translator or DesktopTranslator()
    return translator.text(f"activity.{status if status in _VALID_ACTIVITY_STATUSES else 'failed'}")


def project_command_activity_records(
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse matching lifecycle events into one newest-first command row.

    The journal reader returns newest-first records, so projection walks it in
    reverse to correlate a ``started`` event with its later terminal event.
    Old journals and malformed lifecycle fields remain standalone rows.
    """
    projected: list[tuple[int, dict[str, Any]]] = []
    positions_by_operation: dict[str, int] = {}

    for order, raw_record in enumerate(reversed(records)):
        record = dict(raw_record)
        operation_id = str(record.get("operation_id") or "")
        phase = str(record.get("phase") or "")
        status = str(record.get("status") or "")
        valid_lifecycle = (
            bool(operation_id)
            and phase in _VALID_ACTIVITY_PHASES
            and status in _VALID_ACTIVITY_STATUSES
            and (phase != "started" or status == "running")
            and (phase != "completed" or status in _TERMINAL_ACTIVITY_STATUSES)
        )
        if not valid_lifecycle:
            derived_status = command_activity_status(record)
            record["activity_status"] = derived_status
            record["is_running"] = derived_status == "running"
            projected.append((order, record))
            continue

        record["activity_status"] = status
        record["is_running"] = status == "running"
        if phase == "started":
            positions_by_operation[operation_id] = len(projected)
            projected.append((order, record))
            continue

        started_position = positions_by_operation.pop(operation_id, None)
        if started_position is None:
            projected.append((order, record))
            continue
        _, started_record = projected[started_position]
        merged = {**started_record, **record}
        merged["activity_status"] = status
        merged["is_running"] = False
        projected[started_position] = (order, merged)

    return [record for _, record in sorted(projected, key=lambda item: item[0], reverse=True)]


def clip_text(value: Any, limit: int) -> str:
    """Collapse whitespace and hard-clip to ``limit`` characters."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def tree_vertical_scroll_position(tree: Any) -> float | None:
    """Return a tree view's current vertical position when it is usable."""
    try:
        position = float(tree.yview()[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    if not math.isfinite(position):
        return None
    return max(0.0, min(1.0, position))


def restore_tree_vertical_scroll_position(tree: Any, position: float | None) -> None:
    """Restore a previously captured tree position after its rows are rebuilt."""
    if position is None:
        return
    try:
        tree.yview_moveto(position)
    except (AttributeError, TypeError, ValueError):
        pass


def activity_view_fingerprint(
    records: Sequence[dict[str, Any]], session_id: str | None
) -> str:
    """Stable marker for the visible command list and its active workplace."""
    payload = {"session_id": session_id, "records": list(records)}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def command_activity_metadata(record: dict[str, Any]) -> str:
    """Burp-style metadata view: transport facts without raw stdout/stderr."""
    stdout = str(record.get("stdout") or "")
    stderr = str(record.get("stderr") or "")
    metadata = {
        "event_id": record.get("event_id"),
        "timestamp": record.get("timestamp"),
        "source": record.get("source"),
        "tool": record.get("tool"),
        "workplace": record.get("chat_id") or None,
        "cwd": record.get("cwd"),
        "status": command_activity_status(record),
        "ok": bool(record.get("ok", False)),
        "exit_code": record.get("exit_code"),
        "timed_out": bool(record.get("timed_out", False)),
        "duration_ms": record.get("duration_ms"),
        "command_truncated": bool(record.get("command_truncated", False)),
        "stdout": {
            "bytes": len(stdout.encode("utf-8", errors="replace")),
            "truncated": bool(record.get("stdout_truncated", False)),
        },
        "stderr": {
            "bytes": len(stderr.encode("utf-8", errors="replace")),
            "truncated": bool(record.get("stderr_truncated", False)),
        },
    }
    return json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)


def command_activity_human_output(
    record: dict[str, Any], translator: DesktopTranslator | None = None
) -> str:
    """Readable response pane for one host command, akin to Burp's response view."""
    translator = translator or DesktopTranslator()
    return "\n".join(
        [
            f"$ {record.get('command') or '(empty command)'}",
            translator.text(
                "activity.human.workplace",
                workplace=record.get("chat_id") or translator.text("activity.shared"),
            ),
            translator.text("activity.human.cwd", cwd=record.get("cwd") or "—"),
            translator.text(
                "activity.human.status",
                status=activity_status_label(command_activity_status(record), translator),
            ),
            translator.text(
                "activity.human.result",
                result=translator.text(
                    "activity.human.success" if record.get("ok") else "activity.human.failure"
                ),
            ),
            translator.text("activity.human.exit", code=record.get("exit_code", "—")),
            translator.text("activity.human.duration", duration=record.get("duration_ms", "—")),
            "",
            "STDOUT",
            str(record.get("stdout") or "(empty)"),
            "",
            "STDERR",
            str(record.get("stderr") or "(empty)"),
        ]
    )


def command_activity_inspector_content(
    record: dict[str, Any], translator: DesktopTranslator | None = None
) -> dict[str, str]:
    """Return the four independent inspector panes for one command call."""
    return {
        "metadata": command_activity_metadata(record),
        "stdout": str(record.get("stdout") or "(empty)"),
        "stderr": str(record.get("stderr") or "(empty)"),
        "human": command_activity_human_output(record, translator),
    }


class ActivityView:
    """Own the session/activity state and, once built, its Tk widgets.

    ``parent=None`` intentionally creates a headless view.  It gives unit
    tests a way to exercise the refresh transaction without a desktop display
    while the dashboard uses the same object with the real Tk parent.
    """

    def __init__(
        self,
        *,
        root: Any,
        tk: Any,
        ttk: Any,
        parent: Any | None,
        workspace_root: Callable[[], Path],
        on_message: Callable[[str, str], None],
        on_refresh: Callable[[], None],
        translator: DesktopTranslator | None = None,
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.workspace_root = workspace_root
        self.on_message = on_message
        self.on_refresh = on_refresh
        self.translator = translator or DesktopTranslator()
        self.bindings = TranslationBindings(self.translator)
        self.sessions: list[WorkspaceSession] = []
        self.session_order_ids: list[str] = []
        self.records: list[dict[str, Any]] = []
        self.running_session_ids: set[str] = set()
        self.visible_session_ids: set[str] = set()
        self.closed_session_ids: set[str] = set()
        self.disabled_session_ids: set[str] = set()
        self.session_selected_id: str | None = None
        self.seen_event_ids: set[str] = set()
        self.activity_snapshot_loaded = False
        self.session_tree: Any = None
        self.session_notice_var: Any = None
        self.workplace_filter_var: Any = None
        self.workplace_filter_entry: Any = None
        self.session_rows_by_iid: dict[str, WorkspaceSession] = {}
        self.session_iids: list[str] = []
        self.activity_tree: Any = None
        self.activity_filter_var: Any = None
        self.command_filter_var: Any = None
        self.command_filter_entry: Any = None
        self.activity_rows_by_iid: dict[str, dict[str, Any]] = {}
        self.activity_iids: list[str] = []
        self.activity_inspector: InspectorTabs | None = None
        self.activity_selected_event_id: str | None = None
        self.activity_render_fingerprint: str | None = None
        self.activity_output_fingerprint: tuple[tuple[str, str], ...] | None = None
        self.activity_sort_key: str | None = None
        self.activity_sort_descending = False
        self.filter_job: Any = None
        self.activity_notebook: Any = None
        self.activity_tab: Any = None
        self.sessions_collapsed = False
        self.input_collapsed = False
        self.output_collapsed = False
        self.activity_parent: Any = None
        self.activity_split_panes: Any = None
        self.activity_vertical_panes: Any = None
        self.sessions_panel: Any = None
        self.sessions_stub: Any = None
        self.input_panel: Any = None
        self.output_panel: Any = None
        self.input_collapse_button: Any = None
        self.output_collapse_button: Any = None
        self.activity_content: Any = None
        if parent is not None:
            self._build(parent)

    def refresh(
        self,
        sessions: Sequence[WorkspaceSession],
        records: Sequence[dict[str, Any]],
    ) -> set[ActivityNotification]:
        """Store both snapshots atomically and return unseen activity chats."""
        sessions_by_id = {session.chat_id: session for session in sessions}
        retained_ids = [
            chat_id for chat_id in self.session_order_ids if chat_id in sessions_by_id
        ]
        retained_id_set = set(retained_ids)
        self.session_order_ids = retained_ids + [
            session.chat_id for session in sessions if session.chat_id not in retained_id_set
        ]
        self.sessions = [sessions_by_id[chat_id] for chat_id in self.session_order_ids]
        self.records = project_command_activity_records(records)
        self.running_session_ids = {
            str(record.get("chat_id"))
            for record in self.records
            if record.get("is_running") and record.get("chat_id")
        }
        available = {session.chat_id for session in self.sessions}
        self.visible_session_ids.intersection_update(available)
        self.closed_session_ids.intersection_update(available)
        self.disabled_session_ids.intersection_update(available)
        if self.session_selected_id not in available or self.session_selected_id in self.closed_session_ids:
            self.session_selected_id = None
        new_activity: set[ActivityNotification] = set()
        for record in self.records:
            event_id = str(record.get("event_id") or "")
            activity_id = str(record.get("operation_id") or event_id)
            if not activity_id or activity_id in self.seen_event_ids:
                continue
            self.seen_event_ids.add(activity_id)
            chat_id = str(record.get("chat_id") or "")
            if self.activity_snapshot_loaded and chat_id:
                new_activity.add(ActivityNotification(chat_id, activity_id))
        self.activity_snapshot_loaded = True
        self._render_sessions()
        self._render_records()
        return new_activity

    def set_translator(self, translator: DesktopTranslator) -> None:
        """Relabel the current view without changing filters, rows, or selection."""
        self.translator = translator
        self.bindings.set_translator(translator)
        self._apply_tree_labels()
        self._apply_collapse_labels()
        if self.activity_inspector is not None:
            for key, label_key in (
                ("metadata", "activity.metadata"),
                ("stdout", "activity.stdout"),
                ("stderr", "activity.stderr"),
                ("human", "activity.human"),
            ):
                self.activity_inspector.set_tab_label(key, translator.text(label_key))
            self.activity_inspector.set_copy_messages(
                empty=translator.text("inspector.copy_empty"),
                success=translator.text("inspector.copy_success"),
                selection_success=translator.text("inspector.copy_selection_success"),
            )
        self.activity_render_fingerprint = None
        self.activity_output_fingerprint = None
        self._render_sessions()
        self._render_records()

    def activate_session(self, chat_id: str) -> bool:
        """Reveal, select, and focus a workplace after a new command arrives."""
        if not chat_id:
            return False
        if self.workplace_filter_var is not None:
            current_filter = self.workplace_filter_var.get().strip().lower()
            if current_filter and current_filter not in chat_id.lower():
                self.workplace_filter_var.set("")
        self.closed_session_ids.discard(chat_id)
        self.disabled_session_ids.discard(chat_id)
        self.visible_session_ids.add(chat_id)
        self.session_selected_id = chat_id
        self._render_sessions()
        self._render_records()
        return True

    def reveal_session(self, chat_id: str) -> bool:
        """Reveal a workplace after activity without changing the operator's focus."""
        if not chat_id:
            return False
        self.closed_session_ids.discard(chat_id)
        self.visible_session_ids.add(chat_id)
        self._render_sessions()
        return True

    def reopen_session(self, chat_id: str) -> bool:
        """Reopen a manually closed session; report whether state changed."""
        if not chat_id or chat_id not in self.closed_session_ids:
            return False
        return self.activate_session(chat_id)

    def _apply_tree_labels(self) -> None:
        if self.session_tree is not None:
            self.session_tree.heading("#0", text=self.translator.text("activity.session"))
            self.session_tree.heading("state", text=self.translator.text("activity.state"))
            self.session_tree.heading("seen", text=self.translator.text("activity.last"))
        if self.activity_tree is not None:
            for key, label_key in (
                ("time", "activity.utc"),
                ("workplace", "activity.workplace"),
                ("status", "activity.status"),
                ("command", "activity.command_input"),
                ("exit", "activity.exit"),
                ("duration", "activity.milliseconds"),
            ):
                self.activity_tree.heading(
                    key,
                    text=self.translator.text(label_key),
                    command=lambda key=key: self.sort_records(key),
                )

    def _apply_collapse_labels(self) -> None:
        if self.input_collapse_button is not None:
            arrow = "▸" if self.input_collapsed else "▾"
            self.input_collapse_button.configure(
                text=f"{arrow} {self.translator.text('action.input')}"
            )
        if self.output_collapse_button is not None:
            arrow = "▸" if self.output_collapsed else "▾"
            self.output_collapse_button.configure(
                text=f"{arrow} {self.translator.text('action.output')}"
            )

    def _render_sessions(self) -> None:
        """Render the workplace rail once its Tk widgets have been attached."""
        if self.session_tree is None:
            return
        existing_items = self.session_tree.get_children()
        scroll_position = tree_vertical_scroll_position(self.session_tree)
        for item in existing_items:
            self.session_tree.delete(item)
        self.session_rows_by_iid = {}
        self.session_iids = []
        workspace_filter = (
            self.workplace_filter_var.get().strip().lower()
            if self.workplace_filter_var is not None
            else ""
        )
        visible_sessions = [
            session
            for session in self.sessions
            if session.chat_id in self.visible_session_ids
            and workspace_filter in session.chat_id.lower()
        ]
        for index, session in enumerate(visible_sessions):
            if session.chat_id in self.closed_session_ids:
                continue
            iid = f"workspace-{index}"
            state = (
                self.translator.text("activity.running")
                if session.chat_id in self.running_session_ids
                else self.translator.text("status.disabled")
                if session.chat_id in self.disabled_session_ids
                else self.translator.text("status.enabled")
            )
            tags = (
                ("running",)
                if session.chat_id in self.running_session_ids
                else ("disabled",)
                if session.chat_id in self.disabled_session_ids
                else ()
            )
            self.session_tree.insert(
                "",
                "end",
                iid=iid,
                text=clip_text(session.chat_id, 26),
                values=(state, format_stream_time(session.last_changed).split(" ")[-1]),
                tags=tags,
            )
            self.session_rows_by_iid[iid] = session
            self.session_iids.append(iid)
        if self.session_selected_id:
            target = next(
                (
                    iid
                    for iid, row in self.session_rows_by_iid.items()
                    if row.chat_id == self.session_selected_id
                ),
                None,
            )
            if target:
                self.session_tree.selection_set(target)
                if not existing_items:
                    self.session_tree.see(target)
        if self.session_notice_var is not None:
            self.session_notice_var.set(
                self.translator.text(
                    "activity.session_notice",
                    visible=len(self.session_iids),
                    total=len(self.sessions),
                    closed=len(self.closed_session_ids),
                    root=self.workspace_root().name,
                )
            )
        restore_tree_vertical_scroll_position(self.session_tree, scroll_position)

    def _render_records(self) -> None:
        """Render the command table once its Tk widgets have been attached."""
        if self.activity_tree is None:
            return
        selected = filter_activity_records_for_session(self.records, self.session_selected_id)
        command_filter = (
            self.command_filter_var.get().strip().lower()
            if self.command_filter_var is not None
            else ""
        )
        if command_filter:
            selected = [
                record
                for record in selected
                if command_filter in " ".join(
                    str(record.get(key) or "")
                    for key in ("command", "chat_id", "activity_status", "stdout", "stderr")
                ).lower()
            ]
        if self.activity_sort_key is not None:
            record_key = {
                "time": "timestamp",
                "workplace": "chat_id",
                "status": "activity_status",
                "exit": "exit_code",
                "duration": "duration_ms",
            }.get(self.activity_sort_key, self.activity_sort_key)
            selected = sorted(
                selected,
                key=lambda record: str(record.get(record_key) or ""),
                reverse=self.activity_sort_descending,
            )
        render_fingerprint = activity_view_fingerprint(selected, self.session_selected_id)
        if render_fingerprint == self.activity_render_fingerprint:
            return
        self.activity_render_fingerprint = render_fingerprint
        filter_name = self.session_selected_id or self.translator.text(
            "activity.all_workplaces"
        )
        if self.activity_filter_var is not None:
            self.activity_filter_var.set(
                self.translator.text(
                    "activity.filter_summary",
                    workplace=filter_name,
                    count=len(selected),
                )
            )
        existing_items = self.activity_tree.get_children()
        scroll_position = tree_vertical_scroll_position(self.activity_tree)
        for item in existing_items:
            self.activity_tree.delete(item)
        self.activity_rows_by_iid = {}
        self.activity_iids = []
        seen: set[str] = set()
        for index, record in enumerate(selected):
            base = str(record.get("event_id") or f"command-{index}")
            iid = base
            suffix = 2
            while iid in seen:
                iid = f"{base}#{suffix}"
                suffix += 1
            seen.add(iid)
            timestamp = str(record.get("timestamp", "")).replace("T", " ").replace("+00:00", "Z")
            command = clip_text(record.get("command", ""), 84)
            status = command_activity_status(record)
            exit_code = (
                "—"
                if status == "running"
                else "timeout"
                if record.get("timed_out")
                else str(record.get("exit_code", "—"))
            )
            duration = record.get("duration_ms")
            duration_text = f"{duration}" if duration is not None else "—"
            self.activity_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    timestamp,
                    clip_text(record.get("chat_id") or "shared", 28),
                    activity_status_label(status, self.translator),
                    command,
                    exit_code,
                    duration_text,
                ),
                tags=(status,),
            )
            self.activity_rows_by_iid[iid] = record
            self.activity_iids.append(iid)
        target = next(
            (
                iid
                for iid, record in self.activity_rows_by_iid.items()
                if str(record.get("event_id") or "") == self.activity_selected_event_id
            ),
            None,
        )
        if target is None and self.activity_iids:
            target = self.activity_iids[0]
        if target is not None:
            self.activity_tree.selection_set(target)
            if not existing_items:
                self.activity_tree.see(target)
            self.show_selected_activity()
        else:
            self.activity_selected_event_id = None
            self.activity_output_fingerprint = None
            empty = self.translator.text("activity.no_commands")
            self._set_activity_outputs(
                {"metadata": empty, "stdout": empty, "stderr": empty, "human": empty}
            )
        restore_tree_vertical_scroll_position(self.activity_tree, scroll_position)

    def _schedule_local_filter(self, _event: Any = None) -> None:
        """Debounce local filters on the Tk loop without creating a worker."""
        if self.root is None:
            self._render_sessions()
            self._render_records()
            return
        if self.filter_job is not None:
            try:
                self.root.after_cancel(self.filter_job)
            except self.tk.TclError:
                pass
        self.filter_job = self.root.after(120, self._apply_local_filter)

    def _apply_local_filter(self) -> None:
        self.filter_job = None
        self._render_sessions()
        self._render_records()

    def clear_local_filters(self) -> None:
        if self.workplace_filter_var is not None:
            self.workplace_filter_var.set("")
        if self.command_filter_var is not None:
            self.command_filter_var.set("")
        self._apply_local_filter()

    def focus_command_filter(self, _event: Any = None) -> str:
        if self.command_filter_entry is not None:
            self.command_filter_entry.focus_set()
        return "break"

    def sort_records(self, key: str) -> None:
        if key == self.activity_sort_key:
            self.activity_sort_descending = not self.activity_sort_descending
        else:
            self.activity_sort_key = key
            self.activity_sort_descending = False
        self._render_records()

    def _build(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.activity_parent = parent
        split_panes = self.ttk.Panedwindow(parent, orient="horizontal")
        split_panes.grid(row=0, column=0, sticky="nsew")
        self.activity_split_panes = split_panes

        sessions = self.ttk.LabelFrame(split_panes, padding=10)
        self.bindings.bind(sessions, "activity.workplaces")
        self.sessions_panel = sessions
        sessions.columnconfigure(0, weight=1)
        sessions.rowconfigure(3, weight=1)
        session_intro = self.ttk.Frame(sessions)
        session_intro.grid(row=0, column=0, columnspan=2, sticky="ew")
        session_intro.columnconfigure(0, weight=1)
        session_intro_label = self.ttk.Label(
            session_intro,
            style="Subtle.TLabel",
            wraplength=225,
        )
        self.bindings.bind(session_intro_label, "activity.folder_source")
        session_intro_label.grid(row=0, column=0, sticky="w")
        self.ttk.Button(
            session_intro, text="‹", width=3, command=self.toggle_sessions_panel
        ).grid(row=0, column=1, sticky="e")
        self.workplace_filter_var = self.tk.StringVar(value="")
        self.workplace_filter_entry = self.ttk.Entry(
            sessions,
            textvariable=self.workplace_filter_var,
        )
        self.workplace_filter_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 3))
        self.workplace_filter_entry.bind("<KeyRelease>", self._schedule_local_filter)
        self.session_notice_var = self.tk.StringVar(
            value=self.translator.text("activity.scanning")
        )
        self.ttk.Label(
            sessions,
            textvariable=self.session_notice_var,
            style="FieldName.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 5))

        session_tree = self.ttk.Treeview(
            sessions, columns=("state", "seen"), show="tree headings", height=18, style="Table.Treeview"
        )
        session_tree.column("#0", width=138, stretch=True)
        session_tree.column("state", width=96, stretch=False, anchor="center")
        session_tree.column("seen", width=72, stretch=False, anchor="center")
        session_tree.tag_configure("running", foreground=PALETTE["running"])
        session_tree.tag_configure("disabled", foreground=PALETTE["text_subtle"])
        session_scrollbar = self.ttk.Scrollbar(
            sessions, orient="vertical", command=session_tree.yview
        )
        session_tree.configure(yscrollcommand=session_scrollbar.set)
        session_tree.grid(row=3, column=0, sticky="nsew")
        session_scrollbar.grid(row=3, column=1, sticky="ns")
        session_tree.bind("<<TreeviewSelect>>", self.show_selected_session)
        self.session_tree = session_tree
        self._apply_tree_labels()

        session_actions = self.ttk.Frame(sessions)
        session_actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        session_actions.columnconfigure(0, weight=1)
        session_actions.columnconfigure(1, weight=1)
        show_all = self.ttk.Button(session_actions, command=self.show_all_sessions)
        self.bindings.bind(show_all, "action.all")
        show_all.grid(
            row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 3)
        )
        enable_tracking = self.ttk.Button(session_actions, command=self.enable_selected_session)
        self.bindings.bind(enable_tracking, "action.enable_tracking")
        enable_tracking.grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=(0, 3))
        disable_tracking = self.ttk.Button(session_actions, command=self.disable_selected_session)
        self.bindings.bind(disable_tracking, "action.disable_tracking")
        disable_tracking.grid(row=1, column=0, sticky="ew", padx=(0, 3))
        close_tab = self.ttk.Button(session_actions, command=self.close_selected_session)
        self.bindings.bind(close_tab, "action.close_tab")
        close_tab.grid(
            row=1, column=1, sticky="ew", padx=(3, 0)
        )
        rescan = self.ttk.Button(sessions, command=self.on_refresh)
        self.bindings.bind(rescan, "action.rescan_folders")
        rescan.grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        session_stub = self.ttk.Frame(split_panes, padding=3)
        self.ttk.Button(
            session_stub, text="›", width=3, command=self.toggle_sessions_panel
        ).pack(anchor="n")
        self.sessions_stub = session_stub

        activity = self.ttk.Frame(split_panes)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(1, weight=1)
        self.activity_content = activity

        toolbar = self.ttk.Frame(activity)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(0, weight=1)
        self.activity_filter_var = self.tk.StringVar(
            value=self.translator.text(
                "activity.filter_summary",
                workplace=self.translator.text("activity.all_workplaces"),
                count=0,
            )
        )
        self.ttk.Label(toolbar, textvariable=self.activity_filter_var, style="Subtle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.command_filter_var = self.tk.StringVar(value="")
        self.command_filter_entry = self.ttk.Entry(toolbar, textvariable=self.command_filter_var, width=24)
        self.command_filter_entry.grid(row=0, column=1, sticky="e", padx=(6, 0))
        self.command_filter_entry.bind("<KeyRelease>", self._schedule_local_filter)
        clear_filters = self.ttk.Button(toolbar, command=self.clear_local_filters)
        self.bindings.bind(clear_filters, "action.clear")
        clear_filters.grid(
            row=0, column=2, sticky="e", padx=(6, 0)
        )
        self.input_collapse_button = self.ttk.Button(
            toolbar, command=self.toggle_input_panel
        )
        self.input_collapse_button.grid(row=0, column=3, sticky="e", padx=(6, 0))
        self.output_collapse_button = self.ttk.Button(
            toolbar, command=self.toggle_output_panel
        )
        self.output_collapse_button.grid(row=0, column=4, sticky="e", padx=(6, 0))
        refresh = self.ttk.Button(toolbar, command=self.on_refresh)
        self.bindings.bind(refresh, "action.refresh")
        refresh.grid(
            row=0, column=5, sticky="e", padx=(6, 0)
        )
        self._apply_collapse_labels()

        vertical_panes = self.ttk.Panedwindow(activity, orient="vertical")
        vertical_panes.grid(row=1, column=0, sticky="nsew")
        self.activity_vertical_panes = vertical_panes

        inputs = self.ttk.LabelFrame(vertical_panes, padding=8)
        self.bindings.bind(inputs, "activity.commands")
        self.input_panel = inputs
        inputs.columnconfigure(0, weight=1)
        inputs.rowconfigure(0, weight=1)
        columns = ("time", "workplace", "status", "command", "exit", "duration")
        tree = self.ttk.Treeview(inputs, columns=columns, show="headings", height=10, style="Table.Treeview")
        for key, width in (
            ("time", 142),
            ("workplace", 130),
            ("status", 108),
            ("command", 360),
            ("exit", 58),
            ("duration", 74),
        ):
            tree.heading(key, command=lambda key=key: self.sort_records(key))
            tree.column(key, width=width, stretch=key == "command")
        scrollbar = self.ttk.Scrollbar(inputs, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.tag_configure("running", foreground=PALETTE["running"])
        tree.tag_configure("succeeded", foreground=PALETTE["success"])
        tree.tag_configure("failed", foreground=PALETTE["danger"])
        tree.tag_configure("timed_out", foreground=PALETTE["warning"])
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self.show_selected_activity)
        self.activity_tree = tree
        self._apply_tree_labels()

        output = self.ttk.LabelFrame(vertical_panes, padding=8)
        self.bindings.bind(output, "activity.output")
        self.output_panel = output
        output.columnconfigure(0, weight=1)
        output.rowconfigure(0, weight=1)
        self.activity_inspector = InspectorTabs(
            root=self.root,
            tk=self.tk,
            ttk=self.ttk,
            parent=output,
            tabs=(
                ("metadata", self.translator.text("activity.metadata")),
                ("stdout", self.translator.text("activity.stdout")),
                ("stderr", self.translator.text("activity.stderr")),
                ("human", self.translator.text("activity.human")),
            ),
            on_message=self.on_message,
            copy_empty_message=self.translator.text("inspector.copy_empty"),
            copy_success_message=self.translator.text("inspector.copy_success"),
            copy_selection_success_message=self.translator.text("inspector.copy_selection_success"),
        )
        self.activity_inspector.grid(row=0, column=0, sticky="nsew")
        copy_tab = self.ttk.Button(output, command=self.copy_selected_activity_output)
        self.bindings.bind(copy_tab, "action.copy_tab")
        copy_tab.grid(
            row=1, column=0, sticky="e", pady=(7, 0)
        )

        vertical_panes.add(inputs, weight=1)
        vertical_panes.add(output, weight=1)
        split_panes.add(sessions, weight=1)
        split_panes.add(activity, weight=3)
        self.root.bind("/", self.focus_command_filter)
        self.root.bind("<Escape>", lambda _event: self.clear_local_filters())

    def set_activity_tab(self, notebook: Any, tab: Any) -> None:
        self.activity_notebook = notebook
        self.activity_tab = tab

    def focus(self) -> None:
        if self.activity_notebook is not None and self.activity_tab is not None:
            self.activity_notebook.select(self.activity_tab)
        if self.root is None or self.tk is None:
            return
        try:
            self.root.deiconify()
            self.root.lift()
        except self.tk.TclError:
            pass

    def toggle_sessions_panel(self) -> None:
        if self.sessions_panel is None or self.sessions_stub is None or self.activity_parent is None:
            return
        self.sessions_collapsed = not self.sessions_collapsed
        if self.activity_split_panes is not None:
            if self.sessions_collapsed:
                self.activity_split_panes.forget(self.sessions_panel)
                self.activity_split_panes.insert(0, self.sessions_stub, weight=0)
            else:
                self.activity_split_panes.forget(self.sessions_stub)
                self.activity_split_panes.insert(0, self.sessions_panel, weight=1)
            return
        if self.sessions_collapsed:
            self.sessions_panel.grid_remove()
            self.sessions_stub.grid()
            self.activity_parent.columnconfigure(0, minsize=38)
        else:
            self.sessions_stub.grid_remove()
            self.sessions_panel.grid()
            self.activity_parent.columnconfigure(0, minsize=255)

    def toggle_input_panel(self) -> None:
        if self.input_panel is None:
            return
        self.input_collapsed = not self.input_collapsed
        if self.activity_vertical_panes is not None:
            if self.input_collapsed:
                self.activity_vertical_panes.forget(self.input_panel)
            else:
                self.activity_vertical_panes.insert(0, self.input_panel, weight=1)
        elif self.input_collapsed:
            self.input_panel.grid_remove()
        else:
            self.input_panel.grid()
        self._apply_collapse_labels()

    def toggle_output_panel(self) -> None:
        if self.output_panel is None:
            return
        self.output_collapsed = not self.output_collapsed
        if self.activity_vertical_panes is not None:
            if self.output_collapsed:
                self.activity_vertical_panes.forget(self.output_panel)
            else:
                self.activity_vertical_panes.add(self.output_panel, weight=1)
        elif self.output_collapsed:
            self.output_panel.grid_remove()
        else:
            self.output_panel.grid()
        self._apply_collapse_labels()

    def show_selected_session(self, _event: Any = None) -> None:
        if self.session_tree is None:
            return
        selected = self.session_tree.selection()
        row = self.session_rows_by_iid.get(selected[0]) if selected else None
        if row is None:
            return
        self.session_selected_id = row.chat_id
        self._render_records()

    def show_all_sessions(self) -> None:
        self.session_selected_id = None
        if self.session_tree is not None:
            self.session_tree.selection_remove(self.session_tree.selection())
        self._render_records()

    def _selected_session(self) -> WorkspaceSession | None:
        if self.session_tree is None:
            return None
        selected = self.session_tree.selection()
        return self.session_rows_by_iid.get(selected[0]) if selected else None

    def enable_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            self.on_message("warn", self.translator.text("activity.select_to_enable"))
            return
        self.disabled_session_ids.discard(session.chat_id)
        self.session_selected_id = session.chat_id
        self._render_sessions()
        self._render_records()
        self.on_message(
            "success",
            self.translator.text("activity.tracking_enabled", session=session.chat_id),
        )

    def disable_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            self.on_message("warn", self.translator.text("activity.select_to_disable"))
            return
        self.disabled_session_ids.add(session.chat_id)
        self.session_selected_id = session.chat_id
        self._render_sessions()
        self._render_records()
        self.on_message(
            "warn",
            self.translator.text("activity.tracking_disabled", session=session.chat_id),
        )

    def close_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            self.on_message("warn", self.translator.text("activity.select_to_close"))
            return
        self.closed_session_ids.add(session.chat_id)
        self.visible_session_ids.discard(session.chat_id)
        self.disabled_session_ids.discard(session.chat_id)
        self.session_selected_id = None
        self._render_sessions()
        self._render_records()
        self.on_message(
            "warn", self.translator.text("activity.session_closed", session=session.chat_id)
        )

    def _set_activity_outputs(self, contents: dict[str, str]) -> None:
        if self.activity_inspector is None:
            return
        for key, content in contents.items():
            self.activity_inspector.set_content(key, content)

    def show_error(self, text: str) -> None:
        self.activity_render_fingerprint = None
        self.activity_output_fingerprint = None
        self._set_activity_outputs(
            {"metadata": text, "stdout": text, "stderr": text, "human": text}
        )

    def show_selected_activity(self, _event: Any = None) -> None:
        if self.activity_tree is None:
            return
        selected = self.activity_tree.selection()
        record = self.activity_rows_by_iid.get(selected[0]) if selected else None
        if record is None:
            return
        self.activity_selected_event_id = str(record.get("event_id") or "") or None
        contents = command_activity_inspector_content(record, self.translator)
        output_fingerprint = tuple(contents.items())
        if output_fingerprint == self.activity_output_fingerprint:
            return
        self.activity_output_fingerprint = output_fingerprint
        self._set_activity_outputs(contents)

    def copy_selected_activity_output(self) -> None:
        if self.activity_tree is None:
            return
        selected = self.activity_tree.selection()
        record = self.activity_rows_by_iid.get(selected[0]) if selected else None
        if record is None:
            self.on_message("warn", self.translator.text("activity.select_command"))
            return
        if self.activity_inspector is not None:
            self.activity_inspector.copy_active()
