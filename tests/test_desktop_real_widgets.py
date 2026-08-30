import time

import pytest

from app.cli.context import CLIContext
from app.cli.center.persistence import CenterWindowStateStore
from app.cli.desktop_ui import _DesktopDashboard
from app.cli.ui_preferences import UIPreferencesStore


def _status(workspace: str) -> dict:
    return {
        "ok": True,
        "bridge": "ready",
        "server": {"running": True, "pid": 111},
        "tunnel": {"running": True, "pid": 222},
        "url": "https://safe-ui-verification.example/mcp",
        "last_known_url": "https://safe-ui-verification.example/mcp",
        "url_state": "active",
        "connector_ready": True,
        "auth_required": False,
        "workspace": workspace,
    }


def _spin(root, predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        root.update()
        time.sleep(0.01)
    root.update()


@pytest.mark.gui
def test_real_tk_dashboard_exercises_ui_without_real_lifecycle(
    tmp_path,
    monkeypatch,
):
    tkinter = pytest.importorskip("tkinter")
    ttk = pytest.importorskip("tkinter.ttk")
    try:
        root = tkinter.Tk()
    except tkinter.TclError:
        pytest.skip("No Tk display is available")

    root.withdraw()
    monkeypatch.delenv("HOST_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOST_DEFAULT_DIR", raising=False)
    (tmp_path / ".env").write_text(
        f'HOST_WORKSPACE_DIR="{tmp_path}"\n',
        encoding="utf-8",
    )
    chat_root = tmp_path / "chats"
    chat_root.mkdir()
    (chat_root / "chat-alpha").mkdir()
    (chat_root / "chat-beta").mkdir()
    (chat_root / "chat-alpha" / "meta.json").write_text(
        '{"created_at":"2026-08-30T00:00:01+00:00"}',
        encoding="utf-8",
    )
    (chat_root / "chat-beta" / "meta.json").write_text(
        '{"created_at":"2026-08-30T00:00:02+00:00"}',
        encoding="utf-8",
    )
    values = {
        "HOST_WORKSPACE_DIR": str(tmp_path),
        "HOST_CHAT_ROOT": str(chat_root),
        "MCP_PORT": "18427",
    }
    ctx = CLIContext(
        repo_root=tmp_path,
        values=values,
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=1.0,
    )
    lifecycle_calls: list[str] = []

    def safe_start(_repo_root):
        lifecycle_calls.append("start")
        return {"ok": True, "message": "safe start"}

    def safe_restart(_repo_root, _values):
        lifecycle_calls.append("restart")
        return {"ok": True, "message": "safe restart"}

    activity_records = [
        {
            "event_id": "activity-running",
            "operation_id": "op-running",
            "phase": "started",
            "status": "running",
            "chat_id": "chat-alpha",
            "timestamp": "2026-08-30T00:00:02+00:00",
            "command": "python long_task.py",
        },
        {
            "event_id": "activity-done",
            "operation_id": "op-done",
            "phase": "completed",
            "status": "succeeded",
            "chat_id": "chat-beta",
            "timestamp": "2026-08-30T00:00:01+00:00",
            "command": "git status --short",
            "ok": True,
            "exit_code": 0,
            "stdout": "clean\n",
        },
    ]

    def stream(_cursor):
        yield {
            "event": "stream_replay",
            "data": {"phase": "start", "baseline": True},
        }
        yield {
            "id": "log-alpha",
            "event": "workspace_log",
            "data": {
                "ts": "2026-08-30T00:00:01+00:00",
                "severity_text": "INFO",
                "event_category": "file",
                "event_action": "host_read_file",
                "event_outcome": "success",
                "chat_id": "chat-alpha",
            },
        }
        yield {
            "id": "log-beta",
            "event": "workspace_log",
            "data": {
                "ts": "2026-08-30T00:00:02+00:00",
                "severity_text": "ERROR",
                "event_category": "process",
                "event_action": "host_run_command",
                "event_outcome": "failure",
                "chat_id": "chat-beta",
            },
        }
        yield {
            "event": "stream_replay",
            "data": {"phase": "complete"},
        }

    dashboard = None
    try:
        dashboard = _DesktopDashboard(
            root,
            tkinter,
            ttk,
            ctx,
            initial_message=None,
            status_reader=lambda _root, _values: _status(str(tmp_path)),
            start_action=safe_start,
            restart_action=safe_restart,
            activity_reader=lambda _limit: activity_records,
            workspace_log_stream_reader=stream,
            ui_preferences_store=UIPreferencesStore(tmp_path / "ui.json"),
            window_state_store=CenterWindowStateStore(tmp_path / "window.json"),
        )
        root.update()

        # The persistent runtime health badge is independent from transient
        # feedback, and an auth warning remains visible while auth is disabled.
        health_color = dashboard.status_label.cget("foreground")
        assert health_color
        assert dashboard.runtime_view.auth_banner.winfo_manager() == "grid"
        dashboard._set_message("error", "UI-only verification")
        assert dashboard.status_label.cget("foreground") == health_color
        assert dashboard.message_label.cget("foreground")

        # Transient feedback must never reflow the dashboard when message
        # context changes from a short caption to a long session identifier.
        dashboard._set_message("info", "ok")
        root.update_idletasks()
        root.update()
        short_geometry = (
            dashboard.status_bar.winfo_height(),
            dashboard.notebook.winfo_height(),
            dashboard.feedback_slot.winfo_height(),
            dashboard.message_label.winfo_height(),
        )
        dashboard._set_message(
            "info",
            "New command in session "
            "cw-20260830-auto_download_ctf_challenge-fix-all-follow-5e200043-"
            "with-an-even-longer-context-that-must-not-wrap-or-resize-the-layout",
        )
        root.update_idletasks()
        root.update()
        long_geometry = (
            dashboard.status_bar.winfo_height(),
            dashboard.notebook.winfo_height(),
            dashboard.feedback_slot.winfo_height(),
            dashboard.message_label.winfo_height(),
        )
        assert long_geometry == short_geometry
        assert "\n" not in dashboard.feedback_display_var.get()
        assert dashboard.feedback_display_var.get().endswith("…")

        # Real Treeview/filter/inspector widgets are exercised with fixture
        # events, including the same queue path used by the live SSE reader.
        _spin(root, lambda: len(dashboard.workspace_log_view.rows) >= 2)
        dashboard.activity_view.show_all_sessions()
        assert tuple(dashboard.activity_view.activity_tree["columns"]) == (
            "time",
            "status",
            "command",
            "exit",
            "duration",
        )
        assert len(dashboard.activity_view.activity_tree.get_children()) == 2
        session_iids = dashboard.activity_view.session_tree.get_children()
        assert [
            dashboard.activity_view.session_rows_by_iid[iid].chat_id
            for iid in session_iids
        ] == ["chat-alpha", "chat-beta"]

        # Select chat-alpha explicitly, then simulate a new command arriving in
        # chat-beta. The rail may reveal/update beta, but selection and command
        # inspection must stay pinned to the session the user is reading.
        alpha_iid = next(
            iid
            for iid, row in dashboard.activity_view.session_rows_by_iid.items()
            if row.chat_id == "chat-alpha"
        )
        dashboard.activity_view.session_tree.selection_set(alpha_iid)
        dashboard.activity_view.show_selected_session()
        assert dashboard.activity_view.session_selected_id == "chat-alpha"
        dashboard._on_workspace_activity(
            type(
                "Notification",
                (),
                {"chat_id": "chat-beta", "operation_id": "new-beta-command"},
            )()
        )
        root.update()
        assert dashboard.activity_view.session_selected_id == "chat-alpha"
        selected_iid = dashboard.activity_view.session_tree.selection()[0]
        assert (
            dashboard.activity_view.session_rows_by_iid[selected_iid].chat_id
            == "chat-alpha"
        )

        # Continue the broader filter checks in all-session mode.
        dashboard.activity_view.show_all_sessions()
        dashboard.activity_view.command_filter_var.set("git status")
        dashboard.activity_view._apply_local_filter()
        assert len(dashboard.activity_view.activity_tree.get_children()) == 1
        dashboard.activity_view.clear_local_filters()
        assert len(dashboard.activity_view.activity_tree.get_children()) == 2
        dashboard.activity_view.toggle_input_panel()
        assert dashboard.activity_view.input_collapsed is True
        dashboard.activity_view.toggle_input_panel()
        assert dashboard.activity_view.input_collapsed is False

        dashboard.workspace_log_view.chat_filter_var.set("beta")
        dashboard.workspace_log_view.render()
        assert len(dashboard.workspace_log_view.tree.get_children()) == 1
        dashboard.workspace_log_view.select_chip("error")
        assert len(dashboard.workspace_log_view.tree.get_children()) == 1
        dashboard.workspace_log_view.clear_filters()
        assert len(dashboard.workspace_log_view.tree.get_children()) == 2
        dashboard.workspace_log_view.copy_details()
        assert root.clipboard_get()

        # The root owns the advertised keyboard navigation shortcuts.
        assert root.bind("<Control-Key-1>")
        assert root.bind("<Control-Key-2>")
        assert root.bind("<Control-Key-3>")
        assert root.bind("<Control-r>")
        assert root.bind("/")

        # Lifecycle buttons execute injected safe callbacks only.
        dashboard.runtime_view.action_buttons[1].invoke()  # Start / adopt
        _spin(root, lambda: not dashboard.busy)
        dashboard.runtime_view.action_buttons[2].invoke()  # Restart bridge
        _spin(root, lambda: not dashboard.busy)
        assert lifecycle_calls == ["start", "restart"]

        # Workspace Apply writes only the temporary verification .env and then
        # reaches the same injected safe restart callback.
        selected = tmp_path / "workspace-next"
        selected.mkdir()
        dashboard.workspace_var.set(str(selected))
        dashboard.workspace_selection_dirty = True
        dashboard.runtime_view.action_buttons[0].invoke()
        _spin(root, lambda: not dashboard.busy)
        assert lifecycle_calls == ["start", "restart", "restart"]
        assert str(selected) in (tmp_path / ".env").read_text(encoding="utf-8")

        # Language switching is live, preserves view-local state, and must
        # not add any backend lifecycle action.
        lifecycle_before_language = list(lifecycle_calls)
        dashboard.activity_view.command_filter_var.set("needle")
        dashboard.language_buttons["vi"].invoke()
        root.update()
        assert dashboard.translator.language == "vi"
        assert dashboard.activity_view.command_filter_var.get() == "needle"
        assert dashboard.language_buttons["vi"].cget("style") == "LanguageActive.TButton"
        assert lifecycle_calls == lifecycle_before_language
        assert '"language": "vi"' in (tmp_path / "ui.json").read_text(encoding="utf-8")
        assert "BQA_UI_LANGUAGE" not in (tmp_path / ".env").read_text(encoding="utf-8")

        # Keyboard-targeted navigation and compact/wide adaptation reuse the
        # same widget instances instead of rebuilding live views.
        assert dashboard.select_tab("workspace_logs") == "break"
        assert str(dashboard.notebook.select()) == str(
            dashboard.notebook_tabs["workspace_logs"]
        )
        compact_event = type(
            "Event",
            (),
            {"widget": root, "width": 980},
        )()
        dashboard._on_resize(compact_event)
        assert dashboard.compact_layout is True
        assert dashboard.activity_view.sessions_collapsed is True
        wide_event = type(
            "Event",
            (),
            {"widget": root, "width": 1200},
        )()
        dashboard._on_resize(wide_event)
        assert dashboard.compact_layout is False
        assert dashboard.activity_view.sessions_collapsed is False
    finally:
        if dashboard is not None and not dashboard.closed:
            dashboard.close()
        else:
            try:
                root.destroy()
            except tkinter.TclError:
                pass
