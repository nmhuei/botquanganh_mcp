from __future__ import annotations

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.output import emit_json, human_duration, key_values, table


def handle_health(ctx: CLIContext, _args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    result = client.get("/api/v1/health")
    if ctx.json_output:
        emit_json(result)
        return 0
    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    key_values(
        [
            ("Service", result.get("service", "")),
            ("Version", result.get("version", "")),
            ("Status", "healthy" if result.get("ok") else "unhealthy"),
            ("Profile", result.get("profile", "")),
            ("Workspace", result.get("workspace", "")),
            ("Policy", result.get("command_policy", "")),
            ("Uptime", human_duration(metrics.get("uptime_seconds", 0))),
            ("Requests", metrics.get("total_requests", 0)),
            ("Errors", metrics.get("error_count", 0)),
            ("Rate-limit hits", metrics.get("rate_limit_hits", 0)),
            ("Avg latency", f"{metrics.get('avg_latency_ms', 0)} ms"),
        ]
    )
    return 0 if result.get("ok") else 1


def handle_capabilities(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    result = client.get("/api/v1/capabilities")
    selected = [name for name in ("tools", "limits", "host") if getattr(args, name, False)]
    if selected:
        payload = {name: result.get(name) for name in selected}
    else:
        payload = result
    if ctx.json_output:
        emit_json(payload)
        return 0
    if selected == ["tools"]:
        for tool in result.get("tools", []):
            print(tool)
        return 0
    if selected == ["limits"]:
        key_values([(key, value) for key, value in result.get("limits", {}).items()])
        return 0
    if selected == ["host"]:
        key_values([(key, value) for key, value in result.get("host", {}).items()])
        return 0
    key_values(
        [
            ("Service", result.get("service", "")),
            ("Version", result.get("version", "")),
            ("Profile", result.get("profile", "")),
            ("Tools", len(result.get("tools", []))),
            ("Workspace", result.get("host", {}).get("workspace", "")),
            ("Policy", result.get("host", {}).get("command_policy", "")),
        ]
    )
    tools = result.get("tools", [])
    if tools:
        print()
        table(["Tools"], [[tool] for tool in tools])
    return 0
