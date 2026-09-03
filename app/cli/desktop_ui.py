"""Native Tkinter launcher and thin coordinator for UCS-SecretAgent."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from app.activity_log import read_mcp_command_activity
from app.cli.config_view import set_desktop_ui_language, set_workspace_config
from app.cli.context import CLIContext
from app.cli.desktop_views.activity import (
    ActivityNotification,
    ActivityView,
    discover_workspace_sessions,
)
from app.cli.desktop_views.boot import DesktopBootScreen
from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
from app.cli.desktop_views.runtime import (
    BACKEND_DOWN_BADGE,
    RuntimeView,
    runtime_presentation,
)
from app.cli.desktop_views.theme import PALETTE, apply_desktop_theme
from app.cli.desktop_views.workspace_logs import (
    WorkspaceLogView,
    make_workspace_log_stream_reader,
)
from app.cli.lifecycle import process_command_line, read_pid, restart, start, status_data


StatusReader = Callable[[Any, dict[str, str]], dict[str, Any]]
LifecycleAction = Callable[..., dict[str, Any]]
ActivityReader = Callable[[int], list[dict[str, Any]]]
WorkspaceLogStreamReader = Callable[[str | None], Any]

BQA_UI_DAEMON_ENV = "BQA_UI_DAEMON"
DESKTOP_UI_PID_FILENAME = "desktop-ui.pid"
DESKTOP_APP_NAME = "UCS-SecretAgent"
MIN_COMPLETION_TOAST_SECONDS = 10.0
COMPLETION_TOAST_LIFETIME_MS = 6000


class DesktopUIUnavailable(RuntimeError):
    """Raised when the current session cannot create a desktop window."""


class DesktopUILaunchError(RuntimeError):
    """Raised when a detached desktop window cannot be started."""


class DesktopUIAlreadyRunning(RuntimeError):
    """Raised when a live detached desktop window already owns the session."""

    def __init__(self, pid: int) -> None:
        super().__init__(f"{DESKTOP_APP_NAME} đã chạy nền (PID {pid}).")
        self.pid = pid


def backend_badge(
    data: dict[str, Any], translator: DesktopTranslator | None = None
) -> tuple[str, str]:
    """Derive the backend liveness badge from the same data as ``bqa status``."""
    translator = translator or DesktopTranslator()
    if (data.get("server") or {}).get("running"):
        return translator.text("backend.alive"), PALETTE["success"]
    return translator.text("backend.down"), BACKEND_DOWN_BADGE[1]


def _runtime_summary(data: dict[str, Any]) -> tuple[str, str, str]:
    """Compatibility helper retained for callers that render status text only."""
    presentation = runtime_presentation(data)
    return presentation.status, presentation.color, presentation.summary


def completion_fingerprint(data: dict[str, Any]) -> str:
    """Hash the runtime fields used to identify an action completion."""
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
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def completion_toast_due(
    elapsed_seconds: float,
    start_fingerprint: str | None,
    current_fingerprint: str,
    last_fired_fingerprint: str | None,
) -> bool:
    """Return whether a long lifecycle action gets its one completion toast."""
    if elapsed_seconds < MIN_COMPLETION_TOAST_SECONDS:
        return False
    if start_fingerprint is not None and current_fingerprint == start_fingerprint:
        return False
    return current_fingerprint != last_fired_fingerprint


def desktop_ui_pid_path(repo_root: Path) -> Path:
    return Path(repo_root) / "logs" / DESKTOP_UI_PID_FILENAME


def live_desktop_ui_pid(repo_root: Path) -> int | None:
    pid = read_pid(desktop_ui_pid_path(repo_root))
    if pid is None or pid == os.getpid():
        return None
    command = process_command_line(pid).split()
    return pid if "app.cli.main" in command and "ui" in command else None


def register_desktop_ui_pid(repo_root: Path, pid: int) -> None:
    path = desktop_ui_pid_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def release_desktop_ui_pid(repo_root: Path, pid: int) -> None:
    path = desktop_ui_pid_path(repo_root)
    if read_pid(path) != pid:
        return
    try:
        path.unlink()
    except OSError:
        pass


def graphical_session_available(environ: dict[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    if sys.platform in {"win32", "darwin"}:
        return True
    return bool(values.get("DISPLAY") or values.get("WAYLAND_DISPLAY"))


def desktop_app_icon_path() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "ucs-secretagent.png"


def load_desktop_icon(root: Any, tk: Any) -> Any | None:
    try:
        image = tk.PhotoImage(file=str(desktop_app_icon_path()))
        root.iconphoto(True, image)
        return image
    except (OSError, tk.TclError):
        return None


def launch_desktop_ui_detached(ctx: CLIContext) -> int:
    """Start the desktop UI independently from the invoking terminal session."""
    existing = live_desktop_ui_pid(ctx.repo_root)
    if existing is not None:
        raise DesktopUIAlreadyRunning(existing)
    log_dir = ctx.repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "app.cli.main", "ui"]
    child_env = dict(os.environ)
    child_env[BQA_UI_DAEMON_ENV] = "1"
    try:
        with (log_dir / "desktop-ui.log").open("ab", buffering=0) as log_file:
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
            f"Không thể khởi động {DESKTOP_APP_NAME} nền: {exc}"
        ) from exc
    register_desktop_ui_pid(ctx.repo_root, process.pid)
    return process.pid


class _DesktopDashboard:
    """Coordinate three views, lifecycle actions, refresh scheduling, and shutdown."""

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
        workspace_log_stream_reader: WorkspaceLogStreamReader | None = None,
    ) -> None:
        self.root, self.tk, self.ttk, self.ctx = root, tk, ttk, ctx
        self.status_reader = status_reader
        self.start_action = start_action
        self.restart_action = restart_action
        self.activity_reader = activity_reader
        self.busy = False
        self.closed = False
        self.refresh_job: Any = None
        self.workspace_selection_dirty = False
        self.latest_status_data: dict[str, Any] | None = None
        self.action_started_at: float | None = None
        self.action_start_fingerprint: str | None = None
        self.action_queue: queue.Queue[tuple[str, str, float]] = queue.Queue()
        self.action_drain_job: Any = None
        self.last_toast_fingerprint: str | None = None
        self.active_toast: Any = None
        self.translator = DesktopTranslator(ctx.values.get("BQA_UI_LANGUAGE", "en"))
        self.header_bindings = TranslationBindings(self.translator)
        self.language_choices: dict[str, str] = {}
        self.language_display_var = tk.StringVar()
        self.language_combo: Any = None
        self.notebook: Any = None
        self.notebook_tabs: dict[str, Any] = {}
        self.runtime_view = RuntimeView(
            tk,
            (initial_message or ("", ""))[1],
            self.translator,
        )
        self.values = self.runtime_view.values
        self.status_var = self.runtime_view.status_var
        self.backend_var = self.runtime_view.backend_var
        self.message_var = self.runtime_view.message_var
        self.workspace_var = tk.StringVar(value=ctx.values.get("HOST_WORKSPACE_DIR", ""))
        self.refresh_var = tk.StringVar(value="refresh: —")
        self.sse_var = tk.StringVar(value="SSE: CONNECTING")
        self.status_label: Any = None
        self.backend_label: Any = None
        self.activity_view: ActivityView | None = None
        self.workspace_log_view: WorkspaceLogView | None = None
        self._build(initial_message, workspace_log_stream_reader)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        if self.workspace_log_view is not None:
            self.workspace_log_view.start_stream()

    def _build(
        self,
        initial_message: tuple[str, str] | None,
        workspace_log_stream_reader: WorkspaceLogStreamReader | None,
    ) -> None:
        self.root.title(DESKTOP_APP_NAME)
        self.desktop_icon = load_desktop_icon(self.root, self.tk)
        self.root.geometry("1120x720")
        self.root.minsize(980, 680)
        style = self.ttk.Style(self.root)
        apply_desktop_theme(style, self.root)

        container = self.ttk.Frame(self.root, style="App.TFrame", padding=(12, 10))
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        header = self.ttk.Frame(container, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        brand = self.ttk.Frame(header, style="App.TFrame")
        brand.grid(row=0, column=0, sticky="w")
        brand.columnconfigure(1, weight=1)
        try:
            self.header_icon = self.desktop_icon.subsample(10, 10) if self.desktop_icon is not None else None
        except self.tk.TclError:
            self.header_icon = None
        if self.header_icon is not None:
            self.ttk.Label(brand, image=self.header_icon, style="Brand.TLabel").grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 9)
            )
        brand_name = self.ttk.Label(brand, style="Header.TLabel")
        self.header_bindings.bind(brand_name, "app.identity")
        brand_name.grid(row=0, column=1, sticky="w")
        brand_subtitle = self.ttk.Label(brand, style="Subtle.TLabel")
        self.header_bindings.bind(brand_subtitle, "app.subtitle")
        brand_subtitle.grid(row=1, column=1, sticky="w")
        self.status_label = self.ttk.Label(header, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 12))
        actions = self.ttk.Frame(header, style="App.TFrame")
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        language_label = self.ttk.Label(actions, style="Subtle.TLabel")
        self.header_bindings.bind(language_label, "label.language")
        language_label.pack(side="left", padx=(0, 5))
        self.language_combo = self.ttk.Combobox(
            actions,
            textvariable=self.language_display_var,
            state="readonly",
            width=11,
            style="Language.TCombobox",
        )
        self._refresh_language_selector()
        self.language_combo.bind("<<ComboboxSelected>>", self.change_language)
        self.language_combo.pack(side="left", padx=(0, 10))
        self._add_action(actions, "action.start", self.start_service)
        self._add_action(actions, "action.restart", self.restart_bridge)
        self._add_action(actions, "action.refresh", self.refresh)
        close_button = self.ttk.Button(actions, style="Toolbar.TButton", command=self.close)
        self.header_bindings.bind(close_button, "action.close")
        close_button.pack(side="left")

        notebook = self.ttk.Notebook(container, style="App.TNotebook")
        notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 6))
        runtime_tab = self.ttk.Frame(notebook, padding=14)
        workspace_logs_tab = self.ttk.Frame(notebook, padding=14)
        activity_tab = self.ttk.Frame(notebook, padding=14)
        notebook.add(runtime_tab)
        notebook.add(workspace_logs_tab)
        notebook.add(activity_tab)
        self.notebook = notebook
        self.notebook_tabs = {
            "runtime": runtime_tab,
            "workspace_logs": workspace_logs_tab,
            "gpt_activity": activity_tab,
        }
        self._apply_notebook_labels()
        self.runtime_view.build(
            ttk=self.ttk,
            parent=runtime_tab,
            workspace_var=self.workspace_var,
            on_copy_endpoint=self.copy_endpoint,
            on_choose_workspace=self.choose_workspace,
            on_apply_workspace=self.apply_workspace,
        )
        self.activity_view = ActivityView(
            root=self.root,
            tk=self.tk,
            ttk=self.ttk,
            parent=activity_tab,
            workspace_root=self.chat_workspaces_root,
            on_message=self._set_message,
            on_refresh=self.refresh,
            translator=self.translator,
        )
        self.activity_view.set_activity_tab(notebook, activity_tab)
        self.workspace_log_view = WorkspaceLogView(
            root=self.root,
            tk=self.tk,
            ttk=self.ttk,
            parent=workspace_logs_tab,
            stream_reader=workspace_log_stream_reader or make_workspace_log_stream_reader(self.ctx),
            on_new_activity=self._on_workspace_activity,
            on_message=self._set_message,
            on_status_change=self._set_sse_status,
            translator=self.translator,
        )
        status_bar = self.ttk.Frame(container, style="App.TFrame")
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.columnconfigure(4, weight=1)
        self.backend_label = self.ttk.Label(status_bar, textvariable=self.backend_var, style="Subtle.TLabel")
        self.backend_label.grid(row=0, column=0, sticky="w")
        self.ttk.Label(status_bar, textvariable=self.workspace_var, style="Subtle.TLabel").grid(row=0, column=1, sticky="w", padx=(14, 0))
        self.ttk.Label(status_bar, textvariable=self.refresh_var, style="Subtle.TLabel").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.ttk.Label(status_bar, textvariable=self.sse_var, style="Subtle.TLabel").grid(row=0, column=3, sticky="w", padx=(14, 0))
        self.ttk.Label(status_bar, textvariable=self.message_var, style="Subtle.TLabel", wraplength=400).grid(row=0, column=4, sticky="e", padx=(14, 0))
        if initial_message:
            self._set_message(*initial_message)

    def _language_options(self) -> dict[str, str]:
        return {
            self.translator.text("language.en"): "en",
            self.translator.text("language.vi"): "vi",
        }

    def _refresh_language_selector(self) -> None:
        self.language_choices = self._language_options()
        selected = next(
            label
            for label, language in self.language_choices.items()
            if language == self.translator.language
        )
        self.language_display_var.set(selected)
        if self.language_combo is not None:
            self.language_combo.configure(values=tuple(self.language_choices))

    def _apply_notebook_labels(self) -> None:
        if self.notebook is None:
            return
        for key, tab in self.notebook_tabs.items():
            self.notebook.tab(tab, text=self.translator.text(f"tab.{key}"))

    def change_language(self, _event: Any = None) -> None:
        """Persist and apply the desktop language without resetting live view state."""
        language = self.language_choices.get(self.language_display_var.get())
        if language is None:
            self._refresh_language_selector()
            return
        if language == self.translator.language:
            return
        try:
            updated = set_desktop_ui_language(self.ctx.repo_root, language)
        except ValueError as exc:
            self._refresh_language_selector()
            self._set_message(
                "error", self.translator.text("message.language_error", error=str(exc))
            )
            return
        self.ctx.values.update(updated)
        self.translator = DesktopTranslator(updated["BQA_UI_LANGUAGE"])
        self.header_bindings.set_translator(self.translator)
        self._refresh_language_selector()
        self._apply_notebook_labels()
        self.runtime_view.set_translator(self.translator)
        if self.activity_view is not None:
            self.activity_view.set_translator(self.translator)
        if self.workspace_log_view is not None:
            self.workspace_log_view.set_translator(self.translator)
        self._set_message(
            "success",
            self.translator.text(
                "message.language_saved",
                language=self.translator.text(f"language.{self.translator.language}"),
            ),
        )

    def _add_action(self, parent: Any, text_key: str, command: Callable[[], None]) -> None:
        button = self.ttk.Button(parent, style="Toolbar.TButton", command=command)
        self.header_bindings.bind(button, text_key)
        button.pack(side="left", padx=(0, 7))
        self.runtime_view.action_buttons.append(button)

    def _set_message(self, kind: str, text: str) -> None:
        colors = {
            "success": PALETTE["success"],
            "warn": PALETTE["warning"],
            "error": PALETTE["danger"],
        }
        self.runtime_view.set_message(text)
        if self.status_label is not None:
            self.status_label.configure(foreground=colors.get(kind, PALETTE["text_muted"]))

    def chat_workspaces_root(self) -> Path:
        configured = self.ctx.values.get("HOST_CHAT_ROOT", "").strip()
        if configured:
            return Path(configured).expanduser()
        return Path.home() / "Downloads" / "bqa-workspaces"

    def _on_workspace_activity(self, notification: ActivityNotification) -> None:
        """Reveal new activity while preserving the operator's current focus."""
        if self.activity_view is not None:
            self.activity_view.reveal_session(notification.chat_id)

    def _set_sse_status(self, state: str) -> None:
        self.sse_var.set(f"SSE: {state.upper()}")

    def refresh(self) -> None:
        if self.closed:
            return
        self.refresh_job = None
        try:
            data = self.status_reader(self.ctx.repo_root, self.ctx.values)
            presentation = self.runtime_view.render(data)
            self.latest_status_data = data
            if self.status_label is not None:
                self.status_label.configure(foreground=presentation.color)
            badge_text, badge_color = backend_badge(data, self.translator)
            self.backend_var.set(badge_text)
            if self.backend_label is not None:
                self.backend_label.configure(foreground=badge_color)
            if not self.busy:
                self.runtime_view.set_message(presentation.summary)
            if not self.workspace_selection_dirty:
                self.workspace_var.set(data.get("workspace", self.workspace_var.get()))
        except Exception as exc:
            self.status_var.set(self.translator.text("status.needs_attention"))
            if self.status_label is not None:
                self.status_label.configure(foreground=PALETTE["danger"])
            self.backend_var.set(BACKEND_DOWN_BADGE[0])
            if self.backend_label is not None:
                self.backend_label.configure(foreground=BACKEND_DOWN_BADGE[1])
            self.message_var.set(
                self.translator.text("message.status_error", error=str(exc))
            )
        finally:
            self.refresh_var.set("refresh: " + time.strftime("%H:%M:%S", time.localtime()))
            if not self.closed:
                self._schedule_refresh()
        if self.activity_view is None:
            return
        try:
            records = self.activity_reader(100)
        except Exception as exc:
            self.activity_view.show_error(
                self.translator.text("message.activity_error", error=str(exc))
            )
            return
        sessions = discover_workspace_sessions(self.chat_workspaces_root())
        for notification in self.activity_view.refresh(sessions, records):
            self._on_workspace_activity(notification)

    def _schedule_refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(2_000, self.refresh)

    def _run_action(self, label: str, action: Callable[[], dict[str, Any]]) -> None:
        if self.busy:
            return
        self.busy = True
        self.action_started_at = time.monotonic()
        self.action_start_fingerprint = completion_fingerprint(self.latest_status_data) if isinstance(self.latest_status_data, dict) else None
        self.runtime_view.set_message(
            self.translator.text("message.running_action", action=label)
        )
        self.runtime_view.set_busy(True)
        self._schedule_action_queue_drain()

        def worker() -> None:
            try:
                result = action()
                outcome = (
                    "success",
                    str(
                        result.get("message")
                        or self.translator.text("message.action_complete", action=label)
                    ),
                ) if result.get("ok", True) else (
                    "error",
                    str(
                        result.get("message")
                        or self.translator.text("message.action_failed", action=label)
                    ),
                )
            except Exception as exc:
                outcome = "error", self.translator.text(
                    "message.action_error", action=label.lower(), error=str(exc)
                )
            elapsed = time.monotonic() - (self.action_started_at or time.monotonic())
            self.action_queue.put((*outcome, elapsed))

        threading.Thread(target=worker, name="bqa-desktop-action", daemon=True).start()

    def _schedule_action_queue_drain(self) -> None:
        if self.closed or self.action_drain_job is not None:
            return
        self.action_drain_job = self.root.after(50, self._drain_action_queue)

    def _drain_action_queue(self) -> None:
        """Finish lifecycle work on Tk's main loop, never the worker thread."""
        self.action_drain_job = None
        while not self.closed:
            try:
                kind, text, elapsed_seconds = self.action_queue.get_nowait()
            except queue.Empty:
                break
            self._finish_action(kind, text, elapsed_seconds=elapsed_seconds)
        if self.busy:
            self._schedule_action_queue_drain()

    def _finish_action(self, kind: str, text: str, elapsed_seconds: float = 0.0) -> None:
        if self.closed:
            return
        self.busy = False
        self.runtime_view.set_busy(False)
        self._set_message(kind, text)
        self.refresh()
        self._maybe_show_completion_toast(text, elapsed_seconds)

    def _maybe_show_completion_toast(self, text: str, elapsed_seconds: float) -> None:
        if not isinstance(self.latest_status_data, dict):
            return
        current = completion_fingerprint(self.latest_status_data)
        if not completion_toast_due(elapsed_seconds, self.action_start_fingerprint, current, self.last_toast_fingerprint):
            return
        self.last_toast_fingerprint = current
        self.show_completion_toast(
            self.translator.text("message.completion_toast", seconds=elapsed_seconds), text
        )

    def show_completion_toast(self, title: str, message: str) -> None:
        try:
            if self.active_toast is not None:
                self.active_toast.destroy()
            toast = self.tk.Toplevel(self.root)
            toast.title(DESKTOP_APP_NAME)
            toast.resizable(False, False)
            toast.configure(bg=PALETTE["surface"], padx=16, pady=12)
            try:
                toast.attributes("-topmost", True)
            except self.tk.TclError:
                pass
            self.tk.Label(
                toast,
                text=title,
                font=("TkDefaultFont", 10, "bold"),
                fg=PALETTE["success"],
                bg=PALETTE["surface"],
            ).pack(anchor="w")
            self.tk.Label(
                toast,
                text=message,
                wraplength=320,
                justify="left",
                fg=PALETTE["text"],
                bg=PALETTE["surface"],
            ).pack(anchor="w", pady=(4, 0))
            toast.update_idletasks()
            toast.geometry(f"+{max(0, toast.winfo_screenwidth() - toast.winfo_reqwidth() - 24)}+{max(0, toast.winfo_screenheight() - toast.winfo_reqheight() - 56)}")
            toast.after(COMPLETION_TOAST_LIFETIME_MS, toast.destroy)
            self.active_toast = toast
        except self.tk.TclError:
            return

    def start_service(self) -> None:
        self._run_action(
            self.translator.text("action.start_adopt"),
            lambda: self.start_action(self.ctx.repo_root),
        )

    def restart_bridge(self) -> None:
        self._run_action(
            self.translator.text("action.restart_bridge"),
            lambda: self.restart_action(self.ctx.repo_root, self.ctx.values),
        )

    def choose_workspace(self) -> None:
        from tkinter import filedialog

        initial = self.workspace_var.get()
        selected = filedialog.askdirectory(
            parent=self.root,
            title=self.translator.text("dialog.choose_workspace"),
            initialdir=initial if initial else None,
            mustexist=True,
        )
        if selected:
            self.workspace_var.set(selected)
            self.workspace_selection_dirty = True
            self._set_message(
                "warn", self.translator.text("message.workspace_selected")
            )

    def apply_workspace(self) -> None:
        selected = self.workspace_var.get()
        self.workspace_selection_dirty = False

        def apply() -> dict[str, Any]:
            self.ctx.values.update(set_workspace_config(self.ctx.repo_root, selected))
            result = self.restart_action(self.ctx.repo_root, self.ctx.values)
            return {
                "ok": bool(result.get("ok", True)),
                "message": self.translator.text("message.workspace_saved"),
            }

        self._run_action(self.translator.text("action.apply"), apply)

    def copy_endpoint(self) -> None:
        endpoint = self.values["endpoint"].get()
        if not endpoint or endpoint == self.translator.text("status.not_available"):
            self._set_message("warn", self.translator.text("message.no_endpoint"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(endpoint)
        self.root.update_idletasks()
        self._set_message("success", self.translator.text("message.endpoint_copied"))

    def close(self) -> None:
        self.closed = True
        if self.workspace_log_view is not None:
            self.workspace_log_view.close()
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        if self.action_drain_job is not None:
            self.root.after_cancel(self.action_drain_job)
            self.action_drain_job = None
        self.root.destroy()


def _start_desktop_boot(root: Any, tk: Any) -> DesktopBootScreen:
    """Hide the dashboard root until the short startup sequence is complete."""
    root.withdraw()
    boot_screen = DesktopBootScreen(root, tk, on_ready=root.deiconify)
    boot_screen.start()
    return boot_screen


def run_desktop_ui(
    ctx: CLIContext,
    *,
    initial_message: tuple[str, str] | None = None,
    status_reader: StatusReader = status_data,
    start_action: LifecycleAction = start,
    restart_action: LifecycleAction = restart,
    activity_reader: ActivityReader = read_mcp_command_activity,
    workspace_log_stream_reader: WorkspaceLogStreamReader | None = None,
) -> int:
    """Open the native window and return only after it is closed."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:  # pragma: no cover - depends on Python build
        raise DesktopUIUnavailable("Python was built without Tkinter.") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise DesktopUIUnavailable("No graphical display is available for the BQA window.") from exc
    boot_screen = _start_desktop_boot(root, tk)
    try:
        _DesktopDashboard(root, tk, ttk, ctx, initial_message=initial_message, status_reader=status_reader, start_action=start_action, restart_action=restart_action, activity_reader=activity_reader, workspace_log_stream_reader=workspace_log_stream_reader)
    except Exception:
        boot_screen.close()
        root.destroy()
        raise
    root.mainloop()
    return 0
