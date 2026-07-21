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
from app.cli.context import CLIContext, extract_global_options
from app.cli.errors import CLIError, EXIT_OPERATION_FAILED, EXIT_USAGE
from app.cli.lifecycle import connector_url, restart, server_restart, start, status_data, stop
from app.cli.output import emit_json, key_values, message
from app.cli.parser import build_parser


def _print_script_result(ctx: CLIContext, result: dict) -> None:
    if ctx.json_output:
        emit_json(result)
        return
    if result.get("stdout"):
        sys.stdout.write(str(result["stdout"]))
    if result.get("stderr"):
        sys.stderr.write(str(result["stderr"]))


def _render_status(ctx: CLIContext, data: dict, *, server_only: bool = False) -> None:
    if ctx.json_output:
        if server_only:
            emit_json(
                {
                    "ok": data["server"]["running"] and data["bridge"] == "ready",
                    "server": data["server"],
                    "bridge": data["bridge"],
                    "tunnel": data["tunnel"],
                    "url": data["url"],
                }
            )
        else:
            emit_json(data)
        return
    rows = []
    if not server_only:
        supervisor = data["supervisor"]
        rows.append(("Supervisor", f"{'running' if supervisor['running'] else 'stopped'}" + (f"  pid={supervisor['pid']}" if supervisor.get("pid") else "")))
    server = data["server"]
    tunnel = data["tunnel"]
    rows.extend(
        [
            ("Server", f"{'running' if server['running'] else 'stopped'}" + (f"  pid={server['pid']}" if server.get("pid") else "")),
            ("Tunnel", f"{'running' if tunnel['running'] else 'stopped'}" + (f"  pid={tunnel['pid']}" if tunnel.get("pid") else "")),
            ("Bridge", data["bridge"]),
            ("URL", data.get("url") or "unavailable"),
        ]
    )
    if not server_only:
        rows.extend(
            [
                ("Auth", "enabled" if data["auth_required"] else "disabled"),
                ("Workspace", data["workspace"]),
            ]
        )
    key_values(rows)


def _confirm_restart(args) -> None:
    if args.yes:
        return
    prompt = "This may replace the current Cloudflare URL. Continue? [y/N] "
    if not sys.stdin.isatty():
        raise CLIError("Full tunnel restart requires --yes in non-interactive mode.", EXIT_USAGE)
    answer = input(prompt).strip().lower()
    if answer not in {"y", "yes"}:
        raise CLIError("Restart cancelled.", EXIT_OPERATION_FAILED)


def _dispatch(ctx: CLIContext, args) -> int:
    command = args.command
    if command == "start":
        _print_script_result(ctx, start(ctx.repo_root))
        return 0
    if command == "stop":
        _print_script_result(ctx, stop(ctx.repo_root))
        return 0
    if command == "restart":
        _confirm_restart(args)
        _print_script_result(ctx, restart(ctx.repo_root))
        return 0
    if command == "status":
        data = status_data(ctx.repo_root, ctx.values)
        _render_status(ctx, data)
        return 0 if data["ok"] else 1
    if command == "url":
        url = connector_url(ctx.repo_root, ctx.values)
        if not url:
            raise CLIError("Connector URL is unavailable.")
        if ctx.json_output:
            emit_json({"ok": True, "url": url})
        else:
            print(url)
        return 0
    if command == "server":
        if args.server_command == "status":
            data = status_data(ctx.repo_root, ctx.values)
            _render_status(ctx, data, server_only=True)
            return 0 if data["server"]["running"] and data["bridge"] == "ready" else 1
        result = server_restart(ctx.repo_root, ctx.values)
        if ctx.json_output:
            emit_json(result)
        else:
            if result.get("stdout"):
                sys.stdout.write(str(result["stdout"]))
            if result.get("stderr"):
                sys.stderr.write(str(result["stderr"]))
            if result["tunnel_preserved"]:
                message("Tunnel PID and URL were preserved.", kind="success", no_color=ctx.no_color)
            else:
                message("Tunnel PID or URL changed unexpectedly.", kind="error", no_color=ctx.no_color)
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
        payload = {"ok": True, "cli": "bqa", "version": VERSION, "service_version": VERSION}
        if ctx.json_output:
            emit_json(payload)
        else:
            print(f"bqa {VERSION}")
        return 0
    raise CLIError(f"Unsupported command: {command}", EXIT_USAGE)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    ctx: CLIContext | None = None
    try:
        args = parser.parse_args(extract_global_options(raw_argv))
        ctx = CLIContext.from_args(args)
        return _dispatch(ctx, args)
    except CLIError as exc:
        json_mode = bool(ctx.json_output) if ctx else "--json" in raw_argv
        no_color = bool(ctx.no_color) if ctx else "--no-color" in raw_argv
        if json_mode:
            emit_json(
                {
                    "ok": False,
                    "error": {
                        "message": exc.message,
                        "exit_code": exc.exit_code,
                        "details": exc.details,
                    },
                },
                stream=sys.stderr,
            )
        else:
            message(exc.message, kind="error", no_color=no_color, stream=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        message("Interrupted.", kind="error", no_color=bool(ctx.no_color) if ctx else False, stream=sys.stderr)
        return 130
    except Exception as exc:
        json_mode = bool(ctx.json_output) if ctx else "--json" in raw_argv
        if json_mode:
            emit_json(
                {"ok": False, "error": {"message": str(exc), "exit_code": 1}},
                stream=sys.stderr,
            )
        else:
            message(str(exc), kind="error", no_color=bool(ctx.no_color) if ctx else False, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
