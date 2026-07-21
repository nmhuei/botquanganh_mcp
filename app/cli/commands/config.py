from __future__ import annotations

from app.cli.config_view import is_secret_key, safe_config, validate_config
from app.cli.context import CLIContext
from app.cli.errors import NotFoundCLIError
from app.cli.output import emit_json, render_checks


def handle_config(ctx: CLIContext, args) -> int:
    command = args.config_command
    env_path = ctx.repo_root / ".env"

    if command == "path":
        if ctx.json_output:
            emit_json({"ok": True, "path": str(env_path)})
        else:
            print(env_path)
        return 0

    if command == "show":
        values = safe_config(ctx.values)
        if ctx.json_output:
            emit_json({"ok": True, "path": str(env_path), "values": values})
        else:
            for key, value in values.items():
                print(f"{key}={value}")
        return 0

    if command == "get":
        key = args.key
        if key not in ctx.values:
            raise NotFoundCLIError(f"Configuration key not found: {key}")
        value = "********" if is_secret_key(key) and ctx.values[key] else ctx.values[key]
        if ctx.json_output:
            emit_json({"ok": True, "key": key, "value": value})
        else:
            print(value)
        return 0

    checks = validate_config(ctx.repo_root, ctx.values)
    strict = bool(getattr(args, "strict", False))
    has_failures = any(check["status"] == "fail" for check in checks)
    has_warnings = any(check["status"] == "warn" for check in checks)
    ok = not has_failures and not (strict and has_warnings)
    if ctx.json_output:
        emit_json(
            {
                "ok": ok,
                "strict": strict,
                "warning_count": sum(check["status"] == "warn" for check in checks),
                "failure_count": sum(check["status"] == "fail" for check in checks),
                "checks": checks,
            }
        )
    else:
        render_checks(checks)
    return 0 if ok else 1
