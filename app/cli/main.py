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
from app.cli.context import (
    GLOBAL_FLAG_OPTIONS,
    GLOBAL_VALUE_OPTIONS,
    CLIContext,
    extract_global_options,
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
from app.cli.progress import progress_for


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


def _run_lifecycle_action(ctx: CLIContext, operation: str, action):
    total = 3 if operation == "stop" else 4
    labels = {
        "start": ("Starting or adopting runtime...", "Started runtime"),
        "restart": ("Restarting MCP bridge...", "Restarted runtime"),
        "stop": ("Stopping managed runtime...", "Stopped runtime"),
        "server_restart": ("Restarting MCP bridge...", "Restarted bridge"),
    }
    working, completed = labels[operation]
    rows = (
        ("supervisor", "tunnel", "server")
        if operation == "stop"
        else ("server", "tunnel", "bridge", "endpoint")
    )
    with progress_for(ctx, working, total=total) as progress:
        progress.set_items(rows)
        status_data(ctx.repo_root, ctx.values)
        result = action()
        runtime = status_data(ctx.repo_root, ctx.values)
        for row in rows:
            progress.complete_item(row)
        progress.finish(completed)
    return result, runtime


def _render_lifecycle_result(
    ctx: CLIContext,
    result: dict,
    *,
    operation: str,
    state: str,
    runtime: dict | None = None,
) -> None:
    payload = {**result, "operation": operation, "status": state}

    url = None
    ready = True
    if operation in {"start", "restart"}:
        ready = bool(runtime and runtime.get("connector_ready"))
        if ready:
            url = runtime.get("url") or connector_url(ctx.repo_root, ctx.values)
        if url:
            payload["url"] = url
        payload["runtime_ready"] = ready

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
    if url:
        # Keep the primary artifact on stdout as one copy-safe line. Progress and
        # summaries live on stderr, so piping `bqa` still yields only the URL.
        emit_quiet(url)
    if not ready and not ctx.json_output and not ctx.quiet:
        renderer.hint("bqa status", "Endpoint not confirmed ready yet; inspect with")
    if ctx.verbose:
        details = []
        if result.get("script"):
            details.append(("Script", result["script"]))
        details.append(("Exit code", result.get("exit_code", 0)))
        if details:
            renderer.facts(details)
        stdout = str(result.get("stdout", "")).strip()
        stderr = str(result.get("stderr", "")).strip()
        if stdout or stderr:
            renderer.section("Process output")
            for line in [*stdout.splitlines(), *stderr.splitlines()]:
                renderer.summary(line)


def _confirm_restart(args) -> None:
    # Kept as a compatibility hook for callers/tests. Restart is now server-only
    # and never needs confirmation because it preserves the Quick Tunnel.
    return None


def _dispatch(ctx: CLIContext, args) -> int:
    command = args.command
    if command == "start":
        result, runtime = _run_lifecycle_action(
            ctx, "start", lambda: start(ctx.repo_root)
        )
        _render_lifecycle_result(
            ctx, result, operation="start", state="started", runtime=runtime
        )
        return 0
    if command == "stop":
        result, runtime = _run_lifecycle_action(
            ctx, "stop", lambda: stop(ctx.repo_root)
        )
        _render_lifecycle_result(
            ctx, result, operation="stop", state="stopped", runtime=runtime
        )
        return 0
    if command == "restart":
        _confirm_restart(args)
        result, runtime = _run_lifecycle_action(
            ctx, "restart", lambda: restart(ctx.repo_root, ctx.values)
        )
        _render_lifecycle_result(
            ctx, result, operation="restart", state="restarted", runtime=runtime
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
        result, _runtime = _run_lifecycle_action(
            ctx,
            "server_restart",
            lambda: server_restart(ctx.repo_root, ctx.values),
        )
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
    index = 0
    while index < len(raw_argv):
        token = raw_argv[index]
        if token == "--":
            break
        if token in GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        matched_value_option = next(
            (
                name
                for name in GLOBAL_VALUE_OPTIONS
                if token == name or token.startswith(name + "=")
            ),
            None,
        )
        if matched_value_option:
            index += 1 if token != matched_value_option else 2
            continue
        if not token.startswith("-"):
            return token
        index += 1
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
            # Bare `bqa` is the human-friendly start command. Route it through
            # the normal parser/dispatcher so it gets the same progress model,
            # JSON/quiet handling, and final copy-safe endpoint as `bqa start`.
            raw_argv = ["start", *raw_argv]
            operation = "start"
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
