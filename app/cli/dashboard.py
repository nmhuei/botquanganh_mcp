"""Small interactive terminal dashboard for the ``bqa`` entry command."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TextIO

from app.cli.context import CLIContext
from app.cli.lifecycle import restart, start, status_data
from app.cli.output import Renderer

StatusReader = Callable[[Any, dict[str, str]], dict[str, Any]]
LifecycleAction = Callable[..., dict[str, Any]]
InputReader = Callable[[str], str]


def interactive_terminal(
    stdin: TextIO | None = None, stdout: TextIO | None = None
) -> bool:
    """Whether an interactive dashboard can safely be presented."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    return bool(getattr(stdin, "isatty", lambda: False)()) and bool(
        getattr(stdout, "isatty", lambda: False)()
    )


def _runtime_label(data: dict[str, Any]) -> tuple[str, str]:
    if data.get("ok"):
        return "running", "Sẵn sàng"
    if data.get("server", {}).get("running") or data.get("tunnel", {}).get("running"):
        return "degraded", "Cần kiểm tra"
    return "stopped", "Đã dừng"


def render_dashboard(
    renderer: Renderer, data: dict[str, Any], message: tuple[str, str] | None = None
) -> None:
    """Render one dashboard frame using the shared terminal visual language."""
    state, state_text = _runtime_label(data)
    endpoint = data.get("url") or data.get("last_known_url") or "chưa có"
    endpoint_state = "đang hoạt động" if data.get("connector_ready") else "không sẵn sàng"

    renderer.header("BQA Control Center", "Quản lý BotQuangAnh Host MCP")
    renderer.blank()
    renderer.status(state, state_text)
    renderer.blank()
    renderer.facts(
        [
            ("MCP bridge", data.get("bridge", "unknown")),
            (
                "Server",
                "running" if data.get("server", {}).get("running") else "stopped",
            ),
            (
                "Cloudflare tunnel",
                "running" if data.get("tunnel", {}).get("running") else "stopped",
            ),
            ("Endpoint", endpoint),
            ("Endpoint state", endpoint_state),
            ("Authentication", "enabled" if data.get("auth_required") else "disabled"),
            ("Workspace", data.get("workspace", "unknown")),
        ]
    )
    if message:
        renderer.blank()
        renderer.summary(message[1], message[0])

    renderer.blank()
    renderer.section("Thao tác")
    renderer.facts(
        [
            ("[s]", "Start/adopt service"),
            ("[r]", "Restart MCP bridge (giữ nguyên tunnel)"),
            ("[u]", "Hiện endpoint để copy"),
            ("[f]", "Làm mới trạng thái"),
            ("[q]", "Thoát"),
        ]
    )
    renderer.blank()


def _clear_terminal(stream: TextIO) -> None:
    if getattr(stream, "isatty", lambda: False)():
        stream.write("\033[2J\033[H")
        stream.flush()


def run_dashboard(
    ctx: CLIContext,
    *,
    initial_message: tuple[str, str] | None = None,
    input_reader: InputReader = input,
    status_reader: StatusReader = status_data,
    start_action: LifecycleAction = start,
    restart_action: LifecycleAction = restart,
    renderer: Renderer | None = None,
    clear_screen: bool = True,
) -> int:
    """Run the keyboard-driven control panel until the user exits."""
    renderer = renderer or Renderer(color_mode=ctx.color)
    message = initial_message

    while True:
        if clear_screen:
            _clear_terminal(renderer.stream)
        data = status_reader(ctx.repo_root, ctx.values)
        render_dashboard(renderer, data, message)

        try:
            choice = input_reader("  Chọn thao tác [s/r/u/f/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0

        if choice in {"q", "quit", "exit"}:
            return 0
        if choice in {"", "f", "refresh"}:
            message = ("success", "Đã làm mới trạng thái.")
            continue
        if choice in {"s", "start"}:
            try:
                start_action(ctx.repo_root)
                message = ("success", "Đã yêu cầu khởi động/adopt service.")
            except Exception as exc:  # The dashboard should remain usable after an action fails.
                message = ("error", f"Không thể khởi động service: {exc}")
            continue
        if choice in {"r", "restart"}:
            try:
                result = restart_action(ctx.repo_root, ctx.values)
                if result.get("ok", True):
                    message = ("success", "MCP bridge đã restart; tunnel được giữ nguyên.")
                else:
                    message = ("error", "Restart bridge không hoàn tất.")
            except Exception as exc:  # The dashboard should remain usable after an action fails.
                message = ("error", f"Không thể restart bridge: {exc}")
            continue
        if choice in {"u", "url", "endpoint"}:
            current = data.get("url") if data.get("connector_ready") else None
            if current:
                message = ("success", f"Endpoint hiện tại (có thể copy): {current}")
            else:
                message = ("warn", "Endpoint chưa sẵn sàng; dùng [s] để khởi động service.")
            continue

        message = ("warn", "Lựa chọn không hợp lệ. Chọn s, r, u, f hoặc q.")
