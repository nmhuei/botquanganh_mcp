from __future__ import annotations

from app.cli.config_view import is_secret_key, safe_config, validate_config
from app.cli.context import CLIContext
from app.cli.errors import NotFoundCLIError
from app.cli.output import emit_json, emit_quiet, renderer_for


def _human_value(key: str, value: str) -> str:
    if is_secret_key(key):
        return "configured" if value else "not configured"
    return value


def handle_config(ctx: CLIContext, args) -> int:
    command = args.config_command
    env_path = ctx.repo_root / ".env"

    if command == "path":
        if ctx.json_output:
            emit_json({"ok": True, "status": "available", "path": str(env_path)})
        elif ctx.quiet:
            emit_quiet(env_path)
        else:
            renderer = renderer_for(ctx)
            renderer.header("Configuration", "Environment file")
            renderer.blank()
            renderer.facts([("Path", env_path)])
        return 0

    if command == "show":
        values = safe_config(ctx.values)
        if ctx.json_output:
            emit_json(
                {
                    "ok": True,
                    "status": "available",
                    "path": str(env_path),
                    "values": values,
                }
            )
        elif ctx.quiet:
            emit_quiet([f"{key}={value}" for key, value in values.items()])
        else:
            renderer = renderer_for(ctx)
            renderer.header("Configuration", "Effective values · secrets protected")
            renderer.blank()
            renderer.facts(
                [
                    (key, _human_value(key, str(ctx.values.get(key, ""))))
                    for key in sorted(ctx.values)
                ]
            )
            renderer.blank()
            renderer.hint("bqa config validate", "Validate with")
        return 0

    if command == "get":
        key = args.key
        if key not in ctx.values:
            raise NotFoundCLIError(f"Configuration key not found: {key}")
        value = _human_value(key, ctx.values[key])
        if ctx.json_output:
            emit_json({"ok": True, "status": "available", "key": key, "value": value})
        elif ctx.quiet:
            emit_quiet(value)
        else:
            renderer = renderer_for(ctx)
            renderer.header("Configuration value", key)
            renderer.blank()
            renderer.facts([(key, value)])
        return 0

    checks = validate_config(ctx.repo_root, ctx.values)
    strict = bool(getattr(args, "strict", False))
    failure_count = sum(check["status"] == "fail" for check in checks)
    warning_count = sum(check["status"] == "warn" for check in checks)
    ok = failure_count == 0 and not (strict and warning_count > 0)
    state = "valid" if ok and warning_count == 0 else "degraded" if ok else "invalid"
    payload = {
        "ok": ok,
        "status": state,
        "strict": strict,
        "warning_count": warning_count,
        "failure_count": failure_count,
        "checks": checks,
    }
    if ctx.json_output:
        emit_json(payload)
    elif ctx.quiet:
        emit_quiet(state)
    else:
        renderer = renderer_for(ctx)
        renderer.header("Configuration validation", "Non-destructive checks")
        renderer.blank()
        renderer.status(
            "success"
            if state == "valid"
            else "warn"
            if state == "degraded"
            else "error",
            state,
        )
        renderer.blank()
        renderer.checks(checks)
        renderer.blank()
        renderer.summary(
            f"{len(checks) - warning_count - failure_count} passed   {warning_count} warnings   {failure_count} failed",
            "success" if ok and warning_count == 0 else "warn" if ok else "error",
        )
        if warning_count or failure_count:
            renderer.blank()
            renderer.hint("bqa doctor --local-only", "Inspect with")
    return 0 if ok else 1
