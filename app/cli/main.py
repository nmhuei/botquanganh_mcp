from __future__ import annotations

import sys
from typing import Sequence

from app.cli import VERSION
from app.cli.commands.command import handle_command
from app.cli.commands.completion import handle_completion
from app.cli.commands.config import handle_config
from app.cli.commands.doctor import handle_doctor
from app.cli.commands.filesystem import handle_filesystem
from app.cli.commands.health import handle_capabilities, handle_health
from app.cli.commands.knowledge import handle_knowledge
from app.cli.commands.logs import handle_logs
from app.cli.config_view import load_env
from app.cli.context import CLIContext, extract_global_options, repo_root
from app.cli.dashboard import interactive_terminal, run_dashboard
from app.cli.desktop_ui import (
    DesktopUIUnavailable,
    graphical_session_available,
    launch_desktop_ui_detached,
    run_desktop_ui,
)
from app.cli.errors import CLIError, EXIT_OPERATION_FAILED, EXIT_USAGE
from app.cli.lifecycle import (
    connector_url,
    restart,
    server_restart,
    start,
    status_data,
    stop,
)
from app.cli.output import Renderer, emit_json, emit_quiet, renderer_for
from app.cli.parser import build_parser


def _process_label(process: dict) -> str:
    state = "running" if process.get("running") else "stopped"
    return f"{state} · pid {process['pid']}" if process.get("pid") else state


def _runtime_state(data: dict, *, server_only: bool = False) -> str:
    if server_only:
        if data["server"]["running"] and data["bridge"] == "ready":
            return "ready"
        return "starting" if data["server"]["running"] else "stopped"
    if data.get("ok"):
        return "running"
    if data["server"]["running"] or data["tunnel"]["running"]:
        return "degraded"
    return "stopped"


def _render_status(ctx: CLIContext, data: dict, *, server_only: bool = False) -> None:
    if ctx.json_output:
        if server_only:
            emit_json(
                {
                    "ok": data["server"]["running"] and data["bridge"] == "ready",
                    "status": _runtime_state(data, server_only=True),
                    "server": data["server"],
                    "bridge": data["bridge"],
                    "tunnel": data["tunnel"],
                    "url": data["url"],
                }
            )
        else:
            emit_json({**data, "status": _runtime_state(data)})
        return

    state = _runtime_state(data, server_only=server_only)
    if ctx.quiet:
        emit_quiet(state)
        return

    renderer = renderer_for(ctx)
    renderer.header(
        "Server status" if server_only else "Runtime status",
        "Local MCP bridge" if server_only else "Host MCP and tunnel supervisor",
    )
    renderer.blank()
    renderer.status(state)
    renderer.blank()

    rows: list[tuple[str, str]] = []
    if not server_only:
        rows.append(("Supervisor", _process_label(data["supervisor"])))
    rows.extend(
        [
            ("Server", _process_label(data["server"])),
            ("Bridge", data["bridge"]),
            ("Tunnel", _process_label(data["tunnel"])),
            ("Endpoint", data.get("url") or "unavailable"),
        ]
    )
    if not server_only:
        rows.extend(
            [
                ("Authentication", "enabled" if data["auth_required"] else "disabled"),
                ("Workspace", data["workspace"]),
            ]
        )
    renderer.facts(rows)
    renderer.blank()
    if state in {"running", "ready"}:
        renderer.summary("Runtime checks passed.", "success")
    elif state == "degraded" or state == "starting":
        renderer.summary("One or more runtime components need attention.", "warn")
    else:
        renderer.summary("Runtime is not active.", "offline")
    renderer.blank()
    renderer.hint("bqa logs server", "Inspect activity with")


def _render_lifecycle_result(
    ctx: CLIContext, result: dict, *, operation: str, state: str
) -> None:
    payload = {**result, "operation": operation, "status": state}

    url = None
    if operation in {"start", "restart"}:
        url = connector_url(ctx.repo_root, ctx.values)
        if url:
            payload["url"] = url

    if ctx.json_output:
        emit_json(payload)
        return
    if ctx.quiet:
        if url:
            emit_quiet(url)
        else:
            emit_quiet(state)
        return

    renderer = renderer_for(ctx)
    renderer.header("Lifecycle", operation.capitalize())
    renderer.blank()
    renderer.status("success", f"Runtime {state}")
    if url:
        renderer.blank()
        renderer.copyable_value("Endpoint · copy-safe", url)
    if ctx.verbose:
        details = []
        if result.get("script"):
            details.append(("Script", result["script"]))
        details.append(("Exit code", result.get("exit_code", 0)))
        if details:
            renderer.blank()
            renderer.facts(details)
        stdout = str(result.get("stdout", "")).strip()
        stderr = str(result.get("stderr", "")).strip()
        if stdout or stderr:
            renderer.blank()
            renderer.section("Process output")
            for line in [*stdout.splitlines(), *stderr.splitlines()]:
                renderer.summary(line)
    renderer.blank()
    renderer.hint("bqa status", "Verify with")


def _confirm_restart(args) -> None:
    # Kept as a compatibility hook for callers/tests. Restart is now server-only
    # and never needs confirmation because it preserves the Quick Tunnel.
    return None


def _dispatch(ctx: CLIContext, args) -> int:
    command = args.command
    if command == "start":
        _render_lifecycle_result(
            ctx, start(ctx.repo_root), operation="start", state="started"
        )
        return 0
    if command == "stop":
        _render_lifecycle_result(
            ctx, stop(ctx.repo_root), operation="stop", state="stopped"
        )
        return 0
    if command == "restart":
        _confirm_restart(args)
        _render_lifecycle_result(
            ctx, restart(ctx.repo_root, ctx.values), operation="restart", state="restarted"
        )
        return 0
    if command == "status":
        data = status_data(ctx.repo_root, ctx.values)
        _render_status(ctx, data)
        return 0 if data["ok"] else 1
    if command == "url":
        runtime = status_data(ctx.repo_root, ctx.values)
        url = runtime.get("url") if runtime.get("connector_ready") else None
        if not url:
            last_known = runtime.get("last_known_url")
            detail = f" Last known URL: {last_known}" if last_known else ""
            raise CLIError(f"Quick Tunnel is not active.{detail}")
        if ctx.json_output:
            emit_json({"ok": True, "status": "available", "url": url})
        elif ctx.quiet:
            emit_quiet(url)
        else:
            renderer = renderer_for(ctx)
            renderer.header("Connector URL", "Current public MCP endpoint")
            renderer.blank()
            renderer.status("success", "Endpoint available")
            renderer.blank()
            renderer.copyable_value("Endpoint · copy-safe", url)
            renderer.blank()
            renderer.hint("bqa url --quiet", "Copy URL only")
            renderer.hint("bqa --public health", "Check it with")
        return 0
    if command == "help":
        topic = getattr(args, "topic", None)
        p = build_parser()
        if topic:
            try:
                p.parse_args([topic, "--help"])
            except CLIError:
                pass
        else:
            p.print_help()
        return 0
    if command == "server":
        if args.server_command == "status":
            data = status_data(ctx.repo_root, ctx.values)
            _render_status(ctx, data, server_only=True)
            return 0 if data["server"]["running"] and data["bridge"] == "ready" else 1
        result = server_restart(ctx.repo_root, ctx.values)
        if ctx.json_output:
            emit_json(result)
        elif ctx.quiet:
            emit_quiet("ready" if result["ok"] else "failed")
        else:
            renderer = renderer_for(ctx)
            renderer.header("Server restart", "Tunnel-safe bridge operation")
            renderer.blank()
            renderer.status(
                "success" if result["ok"] else "error",
                "Bridge restarted" if result["ok"] else "Bridge restart failed",
            )
            renderer.blank()
            renderer.facts(
                [
                    ("Bridge", result.get("after", {}).get("bridge", "unknown")),
                    (
                        "Server",
                        _process_label(result.get("after", {}).get("server", {})),
                    ),
                    (
                        "Tunnel preserved",
                        "yes" if result.get("tunnel_preserved") else "no",
                    ),
                ]
            )
            renderer.blank()
            if result.get("tunnel_preserved"):
                renderer.summary("Tunnel PID and URL were preserved.", "success")
            else:
                renderer.summary("Tunnel PID or URL changed unexpectedly.", "error")
            renderer.blank()
            renderer.hint("bqa server status", "Verify with")
        return 0 if result["ok"] else 1
    if command == "health":
        return handle_health(ctx, args)
    if command == "capabilities":
        return handle_capabilities(ctx, args)
    if command == "fs":
        return handle_filesystem(ctx, args)
    if command == "cmd":
        return handle_command(ctx, args)
    if command == "knowledge":
        return handle_knowledge(ctx, args)
    if command == "logs":
        return handle_logs(ctx, args)
    if command == "config":
        return handle_config(ctx, args)
    if command == "doctor":
        return handle_doctor(ctx, args)
    if command == "completion":
        return handle_completion(ctx, args)
    if command == "ui":
        if args.detach:
            if not graphical_session_available():
                raise CLIError("Không có graphical display để mở BQA Control Center.")
            pid = launch_desktop_ui_detached(ctx)
            if ctx.json_output:
                emit_json({"ok": True, "status": "started", "pid": pid})
            elif ctx.quiet:
                emit_quiet(pid)
            else:
                renderer = renderer_for(ctx)
                renderer.header("BQA Control Center", "Detached desktop window")
                renderer.blank()
                renderer.status("success", f"Đã mở nền (PID {pid})")
                renderer.blank()
                renderer.hint("bqa logs launcher -n 100", "Theo dõi service với")
            return 0
        try:
            return run_desktop_ui(ctx)
        except DesktopUIUnavailable:
            if interactive_terminal():
                return run_dashboard(
                    ctx,
                    initial_message=("warn", "Không thể mở cửa sổ desktop; đang dùng TUI."),
                )
            raise CLIError("Không có graphical display. Dùng `bqa tui` trong terminal.")
    if command == "tui":
        return run_dashboard(ctx)
    if command == "version":
        payload = {
            "ok": True,
            "status": "available",
            "cli": "bqa",
            "version": VERSION,
            "service_version": VERSION,
        }
        if ctx.json_output:
            emit_json(payload)
        elif ctx.quiet:
            emit_quiet(VERSION)
        else:
            print(f"bqa {VERSION}")
        return 0
    raise CLIError(f"Unsupported command: {command}", EXIT_USAGE)


def _operation_name(raw_argv: Sequence[str]) -> str:
    for token in raw_argv:
        if token == "--":
            break
        if not token.startswith("-"):
            return token
    return "command"


def _error_hint(exit_code: int, operation: str) -> str:
    if exit_code == EXIT_USAGE:
        return f"bqa {operation} --help" if operation != "command" else "bqa --help"
    if operation in {"status", "health", "server", "doctor"}:
        return "bqa doctor --local-only"
    return "bqa doctor"


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    operation = _operation_name(raw_argv)
    ctx: CLIContext | None = None
    try:
        if not raw_argv or (
            _operation_name(raw_argv) == "command"
            and not any(arg in ("-h", "--help", "--version", "help") for arg in raw_argv)
        ):
            if not any(not arg.startswith("-") for arg in raw_argv if arg != "--"):
                root = repo_root()
                values = load_env(root)
                start(root)
                runtime = status_data(root, values)
                url = runtime.get("url") if runtime.get("connector_ready") else None
                if not url:
                    raise CLIError("Connector URL is unavailable.")
                if not raw_argv and interactive_terminal():
                    parser = build_parser()
                    args = parser.parse_args(["ui"])
                    ctx = CLIContext.from_args(args)
                    if graphical_session_available():
                        try:
                            return run_desktop_ui(
                                ctx,
                                initial_message=("success", "Service đã sẵn sàng."),
                            )
                        except DesktopUIUnavailable:
                            pass
                    return run_dashboard(
                        ctx,
                        initial_message=("success", "Service đã sẵn sàng."),
                    )
                emit_quiet(url)
                return 0
            raw_argv = ["start", *raw_argv]
            operation = _operation_name(raw_argv)
        parser = build_parser()
        args = parser.parse_args(extract_global_options(raw_argv))
        ctx = CLIContext.from_args(args)
        return _dispatch(ctx, args)
    except CLIError as exc:
        json_mode = bool(ctx.json_output) if ctx else "--json" in raw_argv
        quiet_mode = bool(ctx.quiet) if ctx else "--quiet" in raw_argv
        if json_mode:
            emit_json(
                {
                    "ok": False,
                    "status": "error",
                    "operation": operation,
                    "message": exc.message,
                    "exit_code": exc.exit_code,
                    "details": exc.details,
                }
            )
        elif quiet_mode:
            print(exc.message, file=sys.stderr)
        else:
            color = (
                ctx.color if ctx else "never" if "--no-color" in raw_argv else "auto"
            )
            Renderer(color_mode=color, stream=sys.stderr).error(
                f"Could not complete `{operation}`",
                exc.message,
                _error_hint(exc.exit_code, operation),
            )
        return exc.exit_code
    except KeyboardInterrupt:
        if ctx and ctx.json_output:
            emit_json(
                {
                    "ok": False,
                    "status": "error",
                    "operation": operation,
                    "message": "Interrupted by user.",
                    "exit_code": 130,
                }
            )
        else:
            Renderer(
                color_mode=ctx.color if ctx else "auto",
                stream=sys.stderr,
            ).error("Operation interrupted", "Interrupted by user.")
        return 130
    except Exception as exc:
        if ctx and ctx.json_output:
            emit_json(
                {
                    "ok": False,
                    "status": "error",
                    "operation": operation,
                    "message": str(exc),
                    "exit_code": 1,
                }
            )
        elif ctx and ctx.quiet:
            print(str(exc), file=sys.stderr)
        else:
            Renderer(
                color_mode=ctx.color if ctx else "auto",
                stream=sys.stderr,
            ).error(
                f"Could not complete `{operation}`",
                str(exc),
                "bqa doctor",
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
