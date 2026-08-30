#!/usr/bin/env python3
"""Safe visual verification runner for the BQA Center desktop UI.

The runner intentionally injects no-op lifecycle callbacks. --live-readonly may
read the real runtime/activity/log stream, but Start/Restart/Apply can never
restart the real service because the dashboard's writable repo root is a
temporary directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any

from app.activity_log import read_mcp_command_activity
from app.cli.config_view import load_env
from app.cli.context import CLIContext
from app.cli.desktop_ui import _DesktopDashboard
from app.cli.desktop_views.workspace_logs import make_workspace_log_stream_reader
from app.cli.lifecycle import status_data


DEFAULT_SIZES = (
    "980x680",
    "1120x720",
    "1366x768",
    "1600x900",
    "1920x1080",
)


def _fixture_status(workspace: str) -> dict[str, Any]:
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


def _fixture_activity() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "verify-running",
            "operation_id": "verify-op-running",
            "phase": "started",
            "status": "running",
            "chat_id": "chat-alpha",
            "timestamp": "2026-08-30T00:00:03+00:00",
            "command": "python verify_ui.py --safe",
            "cwd": "/safe/workspace",
        },
        {
            "event_id": "verify-success",
            "operation_id": "verify-op-success",
            "phase": "completed",
            "status": "succeeded",
            "chat_id": "chat-beta",
            "timestamp": "2026-08-30T00:00:02+00:00",
            "command": "git status --short",
            "cwd": "/safe/workspace",
            "ok": True,
            "exit_code": 0,
            "duration_ms": 84.2,
            "stdout": "clean\n",
        },
        {
            "event_id": "verify-failed",
            "operation_id": "verify-op-failed",
            "phase": "completed",
            "status": "failed",
            "chat_id": "chat-beta",
            "timestamp": "2026-08-30T00:00:01+00:00",
            "command": "python failing_check.py",
            "cwd": "/safe/workspace",
            "ok": False,
            "exit_code": 1,
            "duration_ms": 32.7,
            "stderr": "verification fixture failure\n",
        },
    ]


def _fixture_stream(_cursor: str | None):
    yield {
        "event": "stream_replay",
        "data": {"phase": "start", "baseline": True},
    }
    for index, data in enumerate(
        (
            {
                "ts": "2026-08-30T00:00:01+00:00",
                "severity_text": "INFO",
                "event_category": "file",
                "event_action": "host_read_file",
                "event_outcome": "success",
                "chat_id": "chat-alpha",
                "event_duration_ms": 4.1,
                "payload": {"path": "README.md"},
            },
            {
                "ts": "2026-08-30T00:00:02+00:00",
                "severity_text": "WARNING",
                "event_category": "process",
                "event_action": "host_run_command",
                "event_outcome": "unknown",
                "chat_id": "chat-beta",
                "event_duration_ms": 13.0,
            },
            {
                "ts": "2026-08-30T00:00:03+00:00",
                "severity_text": "ERROR",
                "event_category": "process",
                "event_action": "host_run_command",
                "event_outcome": "failure",
                "chat_id": "chat-beta",
                "event_duration_ms": 19.0,
            },
        ),
        1,
    ):
        yield {"id": f"verify-log-{index}", "event": "workspace_log", "data": data}
    yield {"event": "stream_replay", "data": {"phase": "complete"}}


def _layout_issues(root: Any) -> list[str]:
    """Return visible-widget clipping issues for the current Tk frame."""
    root.update_idletasks()
    root.update()
    root_x = root.winfo_rootx()
    root_y = root.winfo_rooty()
    root_width = root.winfo_width()
    root_height = root.winfo_height()
    issues: list[str] = []

    def walk(widget: Any) -> None:
        for child in widget.winfo_children():
            try:
                mapped = bool(child.winfo_ismapped())
            except Exception:
                mapped = False
            if mapped:
                x = child.winfo_rootx() - root_x
                y = child.winfo_rooty() - root_y
                width = child.winfo_width()
                height = child.winfo_height()
                if (
                    x < -2
                    or y < -2
                    or x + width > root_width + 2
                    or y + height > root_height + 2
                ):
                    issues.append(
                        f"{child.winfo_class()}:{child} out-of-bounds "
                        f"({x},{y},{width},{height}) in "
                        f"{root_width}x{root_height}"
                    )
                # Catch clipped button/label captions, but ignore intentionally
                # wrapped labels and data widgets such as Entry/Treeview/Text.
                if child.winfo_class() in {"TButton", "TLabel"}:
                    try:
                        text = str(child.cget("text") or "")
                        wrap = int(child.cget("wraplength") or 0)
                    except Exception:
                        text, wrap = "", 0
                    if (
                        text
                        and wrap <= 0
                        and child.winfo_reqwidth() > width + 3
                    ):
                        issues.append(
                            f"{child.winfo_class()}:{child} text clipped: {text!r}"
                        )
            walk(child)

    walk(root)
    return issues


def _capture(root: Any, path: Path) -> None:
    executable = shutil.which("import")
    if not executable:
        raise RuntimeError("ImageMagick import is required for screenshots")
    root.update_idletasks()
    root.update()
    window_id = f"0x{root.winfo_id():x}"
    subprocess.run(
        [executable, "-window", window_id, str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-readonly",
        action="store_true",
        help="Read real status/activity/SSE while lifecycle callbacks remain fake.",
    )
    parser.add_argument(
        "--screenshots-dir",
        type=Path,
        help="Capture the tab/language/size visual matrix into this directory.",
    )
    parser.add_argument(
        "--sizes",
        default=",".join(DEFAULT_SIZES),
        help="Comma-separated WxH screenshot sizes.",
    )
    parser.add_argument(
        "--tk-scaling",
        type=float,
        default=None,
        help="Override Tk text/UI scaling for accessibility verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    real_values = load_env(repo_root)

    import tkinter as tk
    from tkinter import ttk

    with tempfile.TemporaryDirectory(prefix="bqa-ui-verify-") as temp:
        safe_root = Path(temp)
        chat_root = safe_root / "chats"
        for name in ("chat-alpha", "chat-beta", "chat-gamma"):
            (chat_root / name).mkdir(parents=True, exist_ok=True)

        live_chat_root = real_values.get("HOST_CHAT_ROOT", "").strip()
        safe_values = dict(real_values)
        safe_values.update(
            {
                "HOST_WORKSPACE_DIR": str(safe_root),
                "HOST_DEFAULT_DIR": str(safe_root),
                "HOST_CHAT_ROOT": (
                    str(Path(live_chat_root).expanduser())
                    if args.live_readonly and live_chat_root
                    else str(chat_root)
                ),
                "BQA_UI_LANGUAGE": "en",
            }
        )
        (safe_root / ".env").write_text(
            f'HOST_WORKSPACE_DIR="{safe_root}"\n'
            f'HOST_DEFAULT_DIR="{safe_root}"\n'
            'BQA_UI_LANGUAGE="en"\n',
            encoding="utf-8",
        )

        local_port = real_values.get("MCP_PORT", "18427")
        safe_ctx = CLIContext(
            repo_root=safe_root,
            values=safe_values,
            base_url=f"http://127.0.0.1:{local_port}",
            token="",
            request_timeout=2.0,
        )
        lifecycle_calls: list[str] = []

        def safe_start(_repo_root):
            lifecycle_calls.append("start")
            return {"ok": True, "message": "SAFE VERIFY: start callback"}

        def safe_restart(_repo_root, _values):
            lifecycle_calls.append("restart")
            return {"ok": True, "message": "SAFE VERIFY: restart callback"}

        if args.live_readonly:
            real_ctx = CLIContext(
                repo_root=repo_root,
                values=real_values,
                base_url=f"http://127.0.0.1:{local_port}",
                token=real_values.get("GATEWAY_TOKEN", ""),
                request_timeout=2.0,
            )
            status_reader = lambda _root, _values: status_data(repo_root, real_values)
            activity_reader = read_mcp_command_activity
            stream_reader = make_workspace_log_stream_reader(real_ctx)
        else:
            status_reader = lambda _root, _values: _fixture_status(str(safe_root))
            activity_reader = lambda _limit: _fixture_activity()
            stream_reader = _fixture_stream

        root = tk.Tk()
        if args.tk_scaling is not None:
            root.tk.call("tk", "scaling", max(0.5, args.tk_scaling))
        root.title("BQA Center — SAFE UI VERIFICATION")
        dashboard = _DesktopDashboard(
            root,
            tk,
            ttk,
            safe_ctx,
            initial_message=(
                "warn",
                "SAFE UI VERIFICATION · lifecycle mutations disabled",
            ),
            status_reader=status_reader,
            start_action=safe_start,
            restart_action=safe_restart,
            activity_reader=activity_reader,
            workspace_log_stream_reader=stream_reader,
        )
        root.deiconify()

        deadline = time.monotonic() + 0.4
        while time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)

        screenshots: list[str] = []
        layout_issues: dict[str, list[str]] = {}
        if args.screenshots_dir:
            args.screenshots_dir.mkdir(parents=True, exist_ok=True)
            sizes = tuple(
                item.strip()
                for item in args.sizes.split(",")
                if item.strip()
            )
            for language in ("en", "vi"):
                dashboard.change_language(language)
                root.update()
                for tab in ("runtime", "workspace_logs", "gpt_activity"):
                    dashboard.select_tab(tab)
                    root.update()
                    for size in sizes:
                        root.geometry(size)
                        root.update_idletasks()
                        root.update()
                        key = f"{language}-{tab}-{size}"
                        issues = _layout_issues(root)
                        if issues:
                            layout_issues[key] = issues
                        path = (
                            args.screenshots_dir
                            / f"{key}.png"
                        )
                        _capture(root, path)
                        screenshots.append(str(path))

        result = {
            "ok": not layout_issues,
            "mode": "live-readonly" if args.live_readonly else "fixture",
            "lifecycle_calls": lifecycle_calls,
            "lifecycle_mutations_executed": False,
            "screenshots": screenshots,
            "layout_issues": layout_issues,
            "status": dashboard.latest_status_data,
            "language": dashboard.translator.language,
            "tk_scaling": (
                float(root.tk.call("tk", "scaling"))
                if args.tk_scaling is not None
                else None
            ),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        dashboard.close()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
