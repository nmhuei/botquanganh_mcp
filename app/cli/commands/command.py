from __future__ import annotations

import sys

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.errors import PolicyCLIError, TimeoutCLIError
from app.cli.output import emit_json, key_values


def _policy_blocked(result: dict) -> bool:
    return not bool(result.get("allowed", False))


def handle_command(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)

    if args.cmd_command == "check":
        result = client.post(
            "/api/v1/commands/check",
            json_body={"command": args.shell_command},
        )
        if ctx.json_output:
            emit_json(result)
        else:
            key_values(
                [
                    ("Allowed", "yes" if result.get("allowed") else "no"),
                    ("Policy", result.get("policy", "")),
                    ("Commands", ", ".join(result.get("command_names", []))),
                    ("Severity", result.get("severity", "")),
                    ("Rule", result.get("rule", "")),
                    ("Message", result.get("message", "")),
                ]
            )
        return 0 if result.get("allowed") else 5

    if args.check_first:
        policy = client.post(
            "/api/v1/commands/check",
            json_body={"command": args.shell_command},
        )
        if _policy_blocked(policy):
            raise PolicyCLIError(str(policy.get("message") or "Command was blocked by policy."), policy)

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
        if ctx.json_output:
            emit_json(result)
        else:
            if result.get("stdout"):
                sys.stdout.write(str(result["stdout"]))
            if result.get("stderr"):
                sys.stderr.write(str(result["stderr"]))
        raise TimeoutCLIError(str(error.get("message") or "Command timed out."), result)

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
            key_values(
                [
                    ("Exit code", result.get("exit_code")),
                    ("Duration", f"{result.get('duration_ms', 0)} ms"),
                    ("CWD", result.get("cwd", "")),
                    ("Stdout truncated", result.get("stdout_truncated", False)),
                    ("Stderr truncated", result.get("stderr_truncated", False)),
                ],
                stream=sys.stderr,
            )

    try:
        exit_code = int(result.get("exit_code", 1))
    except (TypeError, ValueError):
        exit_code = 1
    if exit_code < 0 or exit_code > 255:
        return 1
    return exit_code
