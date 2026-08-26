"""Native Python desktop control center for BotQuangAnh Host MCP."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

from app.activity_log import read_mcp_command_activity
from app.cli.config_view import set_workspace_config
from app.cli.context import CLIContext
from app.cli.lifecycle import restart, start, status_data

StatusReader = Callable[[Any, dict[str, str]], dict[str, Any]]
LifecycleAction = Callable[..., dict[str, Any]]
ActivityReader = Callable[[int], list[dict[str, Any]]]


class DesktopUIUnavailable(RuntimeError):
    """Raised when the current session cannot create a desktop window."""


class DesktopUILaunchError(RuntimeError):
    """Raised when a detached desktop window cannot be started."""


def graphical_session_available(environ: dict[str, str] | None = None) -> bool:
    """Return whether the current host advertises a graphical desktop session."""
    values = environ if environ is not None else os.environ
    if sys.platform in {"win32", "darwin"}:
        return True
    return bool(values.get("DISPLAY") or values.get("WAYLAND_DISPLAY"))


def launch_desktop_ui_detached(ctx: CLIContext) -> int:
    """Start the desktop UI independently from the invoking terminal session."""
    log_dir = ctx.repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "desktop-ui.log"
    command = [sys.executable, "-m", "app.cli.main", "ui"]
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
            )
    except OSError as exc:
        raise DesktopUILaunchError(
            f"Không thể khởi động BQA Control Center nền: {exc}"
        ) from exc
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
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.ctx = ctx
        self.status_reader = status_reader
        self.start_action = start_action
        self.restart_action = restart_action
        self.activity_reader = activity_reader
        self.busy = False
        self.closed = False
        self.refresh_job: Any = None
        self.workspace_selection_dirty = False
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
        self.message_var = tk.StringVar(value=(initial_message or ("", ""))[1])
        self.status_label: Any = None
        self.action_buttons: list[Any] = []
        self.activity_records: list[dict[str, Any]] = []
        self.activity_tree: Any = None
        self.activity_detail: Any = None
        self._build(initial_message)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

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

        summary = self.ttk.Label(container, textvariable=self.message_var, style="Subtle.TLabel", wraplength=820)
        summary.grid(row=1, column=0, sticky="ew", pady=(18, 12))

        notebook = self.ttk.Notebook(container)
        notebook.grid(row=2, column=0, sticky="nsew")
        runtime_tab = self.ttk.Frame(notebook, padding=14)
        activity_tab = self.ttk.Frame(notebook, padding=14)
        notebook.add(runtime_tab, text="Runtime")
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
            self.status_var.set(state)
            self.status_label.configure(foreground=color)
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
            self.message_var.set(f"Không đọc được trạng thái runtime: {exc}")
        finally:
            if not self.closed:
                self._schedule_refresh()
        self.refresh_activity()

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
        text = " ".join(str(value).split())
        return text if len(text) <= limit else text[: limit - 1] + "…"

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
            if not self.closed:
                self.root.after(0, lambda: self._finish_action(*outcome))

        threading.Thread(target=worker, name="bqa-desktop-action", daemon=True).start()

    def _finish_action(self, kind: str, text: str) -> None:
        if self.closed:
            return
        self.busy = False
        for button in self.action_buttons:
            button.state(["!disabled"])
        self._set_message(kind, text)
        self.refresh()

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
    )
    root.mainloop()
    return 0
