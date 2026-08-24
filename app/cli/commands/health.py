from __future__ import annotations

from app.cli.client import RESTClient
from app.cli.context import CLIContext
from app.cli.output import emit_json, emit_quiet, human_duration, renderer_for
from app.cli.progress import progress_for


def handle_health(ctx: CLIContext, _args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    with progress_for(ctx, "Checking service health...") as progress:
        result = client.get("/api/v1/health")
        progress.finish("Checked service health")
    state = "healthy" if result.get("ok") else "unhealthy"
    payload = {**result, "status": state}
    if ctx.json_output:
        emit_json(payload)
        return 0 if result.get("ok") else 1
    if ctx.quiet:
        emit_quiet(state)
        return 0 if result.get("ok") else 1

    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    renderer = renderer_for(ctx)
    renderer.header("Service health", "REST and host runtime")
    renderer.blank()
    renderer.status(state)
    renderer.blank()
    renderer.facts(
        [
            ("Service", result.get("service", "")),
            ("Version", result.get("version", "")),
            ("Profile", result.get("profile", "")),
            ("Workspace", result.get("workspace", "")),
            ("Policy", result.get("command_policy", "")),
            ("Uptime", human_duration(metrics.get("uptime_seconds", 0))),
            ("Requests", metrics.get("total_requests", 0)),
            ("Errors", metrics.get("error_count", 0)),
            ("Rate-limit hits", metrics.get("rate_limit_hits", 0)),
            ("Average latency", f"{metrics.get('avg_latency_ms', 0)} ms"),
        ]
    )
    renderer.blank()
    error_count = int(metrics.get("error_count", 0) or 0)
    if result.get("ok") and error_count == 0:
        renderer.summary("Service is healthy with no recorded errors.", "success")
    elif result.get("ok"):
        renderer.summary(
            f"Service is healthy with {error_count} recorded errors.", "warn"
        )
    else:
        renderer.summary("Service health check failed.", "error")
    renderer.blank()
    renderer.hint("bqa doctor --local-only", "Inspect diagnostics with")
    return 0 if result.get("ok") else 1


def handle_capabilities(ctx: CLIContext, args) -> int:
    client = RESTClient(ctx.base_url, ctx.token, ctx.request_timeout)
    with progress_for(ctx, "Loading service capabilities...") as progress:
        result = client.get("/api/v1/capabilities")
        progress.finish("Loaded service capabilities")
    selected = [
        name for name in ("tools", "limits", "host") if getattr(args, name, False)
    ]
    payload = {name: result.get(name) for name in selected} if selected else result
    if ctx.json_output:
        emit_json(payload)
        return 0
    if ctx.quiet:
        if selected == ["tools"]:
            emit_quiet(result.get("tools", []))
        elif selected == ["limits"]:
            emit_quiet(
                [f"{key}={value}" for key, value in result.get("limits", {}).items()]
            )
        elif selected == ["host"]:
            emit_quiet(
                [f"{key}={value}" for key, value in result.get("host", {}).items()]
            )
        else:
            emit_quiet(len(result.get("tools", [])))
        return 0

    renderer = renderer_for(ctx)
    renderer.header("Capabilities", "Host MCP surface and limits")
    renderer.blank()
    if selected == ["tools"]:
        tools = result.get("tools", [])
        renderer.status("success", f"{len(tools)} tools available")
        renderer.blank()
        renderer.table(["TOOL"], [[tool] for tool in tools])
        return 0
    if selected == ["limits"]:
        renderer.facts(
            [(key, value) for key, value in result.get("limits", {}).items()]
        )
        return 0
    if selected == ["host"]:
        renderer.facts([(key, value) for key, value in result.get("host", {}).items()])
        return 0

    renderer.status("success", "Capabilities loaded")
    renderer.blank()
    renderer.facts(
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
        renderer.blank()
        renderer.section("Tools")
        renderer.table(["NAME"], [[tool] for tool in tools])
    return 0
