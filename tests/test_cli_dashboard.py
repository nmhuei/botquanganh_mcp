from io import StringIO

from app.cli.context import CLIContext
from app.cli.dashboard import interactive_terminal, run_dashboard
from app.cli.output import Renderer


def _context(tmp_path):
    return CLIContext(
        repo_root=tmp_path,
        values={},
        base_url="http://127.0.0.1:18427",
        token="",
        request_timeout=1,
        color="never",
    )


def _running_status(*_args):
    return {
        "ok": True,
        "bridge": "ready",
        "server": {"running": True},
        "tunnel": {"running": True},
        "url": "https://demo.trycloudflare.com/mcp",
        "last_known_url": "https://demo.trycloudflare.com/mcp",
        "connector_ready": True,
        "auth_required": False,
        "workspace": "/workspace",
    }


def test_dashboard_renders_status_actions_and_endpoint(tmp_path):
    stream = StringIO()
    exit_code = run_dashboard(
        _context(tmp_path),
        input_reader=lambda _prompt: "q",
        status_reader=_running_status,
        renderer=Renderer(color_mode="never", stream=stream, width=100),
        clear_screen=False,
    )

    assert exit_code == 0
    output = stream.getvalue()
    assert "BQA Control Center" in output
    assert "https://demo.trycloudflare.com/mcp" in output
    assert "Restart MCP bridge" in output


def test_dashboard_restart_action_reports_tunnel_safe_success(tmp_path):
    choices = iter(["r", "q"])
    stream = StringIO()
    calls = []

    exit_code = run_dashboard(
        _context(tmp_path),
        input_reader=lambda _prompt: next(choices),
        status_reader=_running_status,
        restart_action=lambda root, values: calls.append((root, values)) or {"ok": True},
        renderer=Renderer(color_mode="never", stream=stream, width=100),
        clear_screen=False,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert "tunnel được giữ nguyên" in stream.getvalue()


def test_dashboard_requires_tty_on_both_streams():
    class Terminal:
        def __init__(self, enabled):
            self.enabled = enabled

        def isatty(self):
            return self.enabled

    assert interactive_terminal(Terminal(True), Terminal(True)) is True
    assert interactive_terminal(Terminal(True), Terminal(False)) is False
