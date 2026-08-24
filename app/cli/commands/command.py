from __future__ import annotations

import sys

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.errors import PolicyCLIError, TimeoutCLIError
from app.cli.output import emit_json, emit_quiet, renderer_for
from app.cli.progress import progress_for


def _policy_blocked(result: dict) -> bool:
    return not bool(result.get("allowed", False))


def handle_command(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)

    if args.cmd_command == "check":
        with progress_for(ctx, "Checking command policy...") as progress:
            result = client.post(
                "/api/v1/commands/check",
                json_body={"command": args.shell_command},
            )
            progress.finish("Checked command policy")
        allowed = bool(result.get("allowed"))
        payload = {**result, "status": "allowed" if allowed else "blocked"}
        if ctx.json_output:
            emit_json(payload)
        elif ctx.quiet:
            emit_quiet("allowed" if allowed else "blocked")
        else:
            renderer = renderer_for(ctx)
            renderer.header("Command policy", "Preflight inspection")
            renderer.blank()
            renderer.status("allowed" if allowed else "blocked")
            renderer.blank()
            renderer.facts(
                [
                    ("Policy", result.get("policy", "")),
                    ("Commands", ", ".join(result.get("command_names", []))),
                    ("Severity", result.get("severity", "")),
                    ("Rule", result.get("rule", "") or "none"),
                    (
                        "Message",
                        result.get("message", "") or "No policy violation detected.",
                    ),
                ]
            )
            renderer.blank()
            if allowed:
                renderer.hint(
                    f"bqa cmd run {args.shell_command!r}",
                    "Execute with",
                )
            else:
                renderer.hint(
                    "bqa knowledge guide --query policy", "Review policy with"
                )
        return 0 if allowed else 5

    progress_total = 2 if args.check_first else None
    initial_message = "Checking command policy..." if args.check_first else "Running command..."
    with progress_for(
        ctx,
        initial_message,
        total=progress_total,
        summary_non_tty=False,
    ) as progress:
        if args.check_first:
            policy = client.post(
                "/api/v1/commands/check",
                json_body={"command": args.shell_command},
            )
            if _policy_blocked(policy):
                raise PolicyCLIError(
                    str(policy.get("message") or "Command was blocked by policy."), policy
                )
            progress.advance("Running command...")

        result = client.post(
            "/api/v1/commands/run",
            json_body={
                "command": args.shell_command,
                "cwd": args.cwd,
                "timeout_seconds": args.timeout,
            },
            allow_command_failure=True,
        )
        error = result.get("error") if isinstance(result, dict) else None
        if isinstance(error, dict) and error.get("code") == "TIMEOUT":
            raise TimeoutCLIError(
                str(error.get("message") or "Command timed out."), result
            )
        if progress_total is not None:
            progress.advance("Completed command")
        progress.finish(
            "Completed command",
            detail=f"exit {result.get('exit_code', 'unknown')}",
        )

    if ctx.json_output:
        emit_json(result)
    else:
        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        if ctx.verbose:
            if stdout and not stdout.endswith("\n"):
                sys.stdout.write("\n")
            renderer = renderer_for(ctx, stream=sys.stderr)
            renderer.facts(
                [
                    ("Exit code", result.get("exit_code")),
                    ("Duration", f"{result.get('duration_ms', 0)} ms"),
                    ("CWD", result.get("cwd", "")),
                    ("Stdout truncated", result.get("stdout_truncated", False)),
                    ("Stderr truncated", result.get("stderr_truncated", False)),
                ]
            )

    try:
        exit_code = int(result.get("exit_code", 1))
    except (TypeError, ValueError):
        exit_code = 1
    if exit_code < 0 or exit_code > 255:
        return 1
    return exit_code
