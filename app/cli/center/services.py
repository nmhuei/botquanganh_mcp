"""Shared presentation/domain services for BQA Center.

This module intentionally contains no Qt/Tk code. It aggregates existing host,
workspace, health, and diagnostic services into stable operator-facing records
that any frontend can render.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from app import chat_sweeper
from app.chat_errors import validate_chat_id
from app.chat_workspace import read_journal_records, summarize_journal_records
from app.cli.config_view import bool_value, resolve_config_path, validate_config
from app.cli.context import normalize_base_url
from app.cli.lifecycle import canonical_tunnel_base, status_data
from app.cli.client import RESTClient
from app.dependency_check import check_project_dependencies
from app.tools.health import get_capabilities, health_check


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_RUNTIME_LOG_FILES = {
    "server": "server.log",
    "tunnel": "cloudflared.log",
    "launcher": "launcher.log",
    "audit": "gateway.log",
    "desktop": "desktop-ui.log",
}


def _iso_from_epoch(value: float | int | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _format_bytes(value: int | float | None) -> str:
    try:
        size = max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"


def workspace_inventory(root: Path) -> list[dict[str, Any]]:
    """Return operator-facing active + archived workspace records."""
    records: list[dict[str, Any]] = []
    for item in chat_sweeper.scan(Path(root)):
        path = Path(str(item["path"]))
        meta: dict[str, Any] = {}
        try:
            raw = json.loads((path / chat_sweeper.META_FILENAME).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                meta = raw
        except (OSError, ValueError):
            pass

        try:
            journal = read_journal_records(path)
            summary = summarize_journal_records(journal)
        except (OSError, ValueError):
            journal = []
            summary = {}

        size = item.get("size_bytes")
        records.append(
            {
                "chatId": str(item.get("chat_id") or path.name),
                "label": str(meta.get("label") or item.get("chat_id") or path.name),
                "path": str(path),
                "workspaceState": "archived" if item.get("archived") else "active",
                "archived": bool(item.get("archived")),
                "metaOk": bool(item.get("meta_ok")),
                "createdAt": str(meta.get("created_at") or ""),
                "lastActive": _iso_from_epoch(item.get("mtime")),
                "lastActiveEpoch": float(item.get("mtime") or 0.0),
                "sizeBytes": int(size or 0),
                "sizeText": _format_bytes(size),
                "events": len(journal),
                "operations": int(summary.get("operations") or 0),
                "failures": int(summary.get("failures") or 0),
            }
        )
    records.sort(
        key=lambda row: (
            bool(row["archived"]),
            -float(row["lastActiveEpoch"]),
            str(row["chatId"]),
        )
    )
    return records


def workspace_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active = [row for row in rows if not row.get("archived")]
    archived = [row for row in rows if row.get("archived")]
    total_bytes = sum(int(row.get("sizeBytes") or 0) for row in rows)
    return {
        "active": len(active),
        "archived": len(archived),
        "total": len(rows),
        "bytes": total_bytes,
        "bytesText": _format_bytes(total_bytes),
        "failures": sum(int(row.get("failures") or 0) for row in active),
    }


def archive_workspace(root: Path, chat_id: str) -> dict[str, Any]:
    validated = validate_chat_id(chat_id)
    target = Path(root) / validated
    if not target.is_dir():
        raise FileNotFoundError(f"Active workspace '{validated}' was not found.")
    result = chat_sweeper.apply_actions(
        [{"action": "ARCHIVE_IDLE", "target": str(target)}],
        Path(root),
        dry_run=False,
    )[0]
    if result.get("status") != "archived":
        raise RuntimeError(str(result.get("detail") or "Workspace archive failed."))
    return {"ok": True, "message": f"Workspace {validated} archived", **result}


def restore_workspace(root: Path, chat_id: str) -> dict[str, Any]:
    validated = validate_chat_id(chat_id)
    root = Path(root)
    source = root / chat_sweeper.ARCHIVE_DIR_NAME / validated
    destination = root / validated
    if destination.exists():
        raise FileExistsError(f"Active workspace '{validated}' already exists.")
    if not source.is_dir():
        raise FileNotFoundError(f"Archived workspace '{validated}' was not found.")
    source.rename(destination)
    return {
        "ok": True,
        "message": f"Workspace {validated} restored",
        "status": "restored",
        "target": str(source),
        "destination": str(destination),
    }


def delete_archived_workspace(root: Path, chat_id: str) -> dict[str, Any]:
    validated = validate_chat_id(chat_id)
    target = Path(root) / chat_sweeper.ARCHIVE_DIR_NAME / validated
    if not target.is_dir():
        raise FileNotFoundError(f"Archived workspace '{validated}' was not found.")
    result = chat_sweeper.apply_actions(
        [{"action": "DELETE_EXPIRED", "target": str(target)}],
        Path(root),
        dry_run=False,
    )[0]
    if result.get("status") != "deleted":
        raise RuntimeError(str(result.get("detail") or "Workspace deletion failed."))
    return {"ok": True, "message": f"Workspace {validated} deleted", **result}


def workspace_prune(
    root: Path,
    values: Mapping[str, Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    limits = chat_sweeper.SweepLimits(
        idle_archive_hours=float(values.get("HOST_CHAT_IDLE_ARCHIVE_HOURS", 72)),
        retention_days=float(values.get("HOST_CHAT_RETENTION_DAYS", 30)),
        max_workspaces=int(values.get("HOST_CHAT_MAX_WORKSPACES", 128)),
        root_max_gb=float(values.get("HOST_CHAT_ROOT_MAX_GB", 24)),
    )
    report = chat_sweeper.run_sweep_once(Path(root), limits, dry_run=not apply)
    report["ok"] = all(
        result.get("status") not in {"error", "refused"}
        for result in report.get("results", [])
    )
    report["apply"] = apply
    report["message"] = (
        f"{len(report.get('actions', []))} workspace lifecycle action(s) "
        + ("applied" if apply else "planned")
    )
    return report


def security_posture(values: Mapping[str, Any]) -> list[dict[str, str]]:
    auth = bool_value(values, "REQUIRE_AUTH", False)
    token_set = bool(str(values.get("GATEWAY_TOKEN") or "").strip())
    restricted = bool_value(values, "HOST_RESTRICT_TO_WORKSPACE", True)
    chat_workspaces = bool_value(values, "HOST_CHAT_WORKSPACES", True)
    isolated = bool_value(values, "HOST_CHAT_ISOLATE", False)
    command_policy = str(values.get("HOST_COMMAND_POLICY") or "guarded").strip().lower()
    attribution = str(values.get("ATTRIBUTION_MODE") or "off").strip().lower()

    return [
        {
            "itemId": "auth",
            "label": "Authentication",
            "value": "Enabled" if auth else "Disabled",
            "tone": "success" if auth and token_set else "error" if auth and not token_set else "warning",
            "detail": (
                "Gateway authentication is enforced."
                if auth and token_set
                else "Authentication is enabled but no gateway token is configured."
                if auth
                else "Safe for trusted local use only; a public connector should require authentication."
            ),
        },
        {
            "itemId": "workspace-restriction",
            "label": "Workspace restriction",
            "value": "Restricted" if restricted else "Unrestricted",
            "tone": "success" if restricted else "warning",
            "detail": "Host file operations are constrained to the configured workspace." if restricted else "Host paths are not restricted to one workspace.",
        },
        {
            "itemId": "command-policy",
            "label": "Command policy",
            "value": command_policy or "unknown",
            "tone": "success" if command_policy in {"guarded", "allowlist"} else "error",
            "detail": "Commands pass through policy inspection before execution.",
        },
        {
            "itemId": "attribution",
            "label": "Attribution",
            "value": attribution or "off",
            "tone": "success" if attribution == "enforce" else "info" if attribution in {"strict", "tag"} else "warning",
            "detail": "Host operations are bound to chat/workspace identity." if attribution == "enforce" else "Attribution is not in enforce mode.",
        },
        {
            "itemId": "chat-workspaces",
            "label": "Chat workspaces",
            "value": "Enabled" if chat_workspaces else "Disabled",
            "tone": "success" if chat_workspaces else "info",
            "detail": "Each chat can receive a dedicated persisted workspace." if chat_workspaces else "Per-chat workspace management is disabled.",
        },
        {
            "itemId": "chat-isolation",
            "label": "Chat write isolation",
            "value": "Enabled" if isolated else "Disabled",
            "tone": "success" if isolated else "info",
            "detail": "Chat writes are confined to the bound chat workspace." if isolated else "Global workspace policy still applies; chat-specific write isolation is off.",
        },
    ]


def health_metric_rows(health: Mapping[str, Any]) -> list[dict[str, str]]:
    metrics = dict(health.get("metrics") or {})
    capacity = dict((health.get("capacity") or {}).get("commands") or {})
    in_use = capacity.get("in_use", capacity.get("active", 0))
    maximum = capacity.get("limit", capacity.get("max", capacity.get("capacity", 0)))
    return [
        {"itemId": "uptime", "label": "Uptime", "value": f"{float(metrics.get('uptime_seconds') or 0):.0f}s", "detail": "Current server process uptime"},
        {"itemId": "requests", "label": "Requests", "value": str(metrics.get("total_requests", 0)), "detail": "HTTP requests handled since start"},
        {"itemId": "errors", "label": "5xx errors", "value": str(metrics.get("error_count", 0)), "detail": "Server-side HTTP failures"},
        {"itemId": "p95", "label": "p95 latency", "value": f"{float(metrics.get('p95_latency_ms') or 0):.1f} ms", "detail": "Snapshot percentile; not a time-series graph"},
        {"itemId": "inflight", "label": "In flight", "value": str(metrics.get("in_flight", 0)), "detail": f"Peak {metrics.get('peak_in_flight', 0)}"},
        {"itemId": "capacity", "label": "Command capacity", "value": f"{in_use}/{maximum}" if maximum else str(in_use), "detail": "Concurrent command executor slots"},
    ]


def overall_health(
    runtime: Mapping[str, Any],
    health: Mapping[str, Any],
    stream_state: str,
    config_checks: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    server = bool((runtime.get("server") or {}).get("running"))
    tunnel = bool((runtime.get("tunnel") or {}).get("running"))
    bridge = str(runtime.get("bridge") or "unknown")
    connector = bool(runtime.get("connector_ready"))
    config_fail = any(row.get("status") == "fail" for row in config_checks or [])
    error_count = int((health.get("metrics") or {}).get("error_count") or 0)
    public_unauth = connector and not bool(runtime.get("auth_required"))

    if config_fail:
        return {"state": "misconfigured", "tone": "error", "title": "Configuration needs attention", "detail": "One or more runtime configuration checks are failing."}
    if not server:
        return {"state": "offline", "tone": "error", "title": "MCP server is stopped", "detail": "The local bridge is not available."}
    if bridge != "ready":
        return {"state": "starting", "tone": "warning", "title": "MCP bridge is starting", "detail": f"Bridge state: {bridge}."}
    if not tunnel:
        return {"state": "local_only", "tone": "warning", "title": "Local MCP is ready", "detail": "The public Cloudflare connector is offline."}
    url_state = str(runtime.get("url_state") or "unavailable")
    if url_state == "stale":
        return {"state": "stale_data", "tone": "warning", "title": "Connector state is stale", "detail": "The tunnel process is running, but only a last-known connector URL is available."}
    if not connector or url_state != "active":
        return {"state": "degraded", "tone": "warning", "title": "Public connector is not confirmed", "detail": "The tunnel process is running, but no active connector URL is currently confirmed."}
    if public_unauth:
        return {"state": "security_warning", "tone": "warning", "title": "Public connector is unauthenticated", "detail": "The connector is live, but REQUIRE_AUTH is disabled."}
    if stream_state.lower() not in {"live", "replaying"}:
        return {"state": "degraded", "tone": "warning", "title": "Runtime ready; activity stream degraded", "detail": f"Activity stream state: {stream_state or 'offline'}."}
    if error_count:
        return {"state": "degraded", "tone": "warning", "title": "Runtime ready with recent server errors", "detail": f"{error_count} server error response(s) recorded since start."}
    return {"state": "healthy", "tone": "success", "title": "All core services are ready", "detail": "Server, bridge, public connector, and live activity stream are available."}


def attention_items(
    runtime: Mapping[str, Any],
    health: Mapping[str, Any],
    stream_state: str,
    config_checks: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(item_id: str, severity: str, title: str, detail: str, action: str = "") -> None:
        rows.append({"itemId": item_id, "severity": severity, "title": title, "detail": detail, "action": action})

    server = bool((runtime.get("server") or {}).get("running"))
    tunnel = bool((runtime.get("tunnel") or {}).get("running"))
    bridge = str(runtime.get("bridge") or "unknown")
    url_state = str(runtime.get("url_state") or "unavailable")
    connector = bool(runtime.get("connector_ready"))

    if not server:
        add("server-offline", "error", "MCP server is stopped", "Host MCP requests cannot be served until the local server is running.", "Start service")
    elif bridge != "ready":
        add("bridge-not-ready", "error", "MCP bridge is not ready", f"Current bridge state: {bridge}.", "Run diagnostics")

    if not tunnel:
        add("tunnel-offline", "warning", "Public connector is offline", "Local MCP may still be usable; public ChatGPT connections cannot reach this host.", "View tunnel logs")
    elif url_state == "stale":
        add("connector-stale", "warning", "Connector URL is stale", "A last-known URL exists but it is not currently confirmed active.", "Refresh")
    elif not connector or url_state != "active":
        add("connector-unconfirmed", "warning", "Public connector is not confirmed", "The tunnel process is running, but there is no confirmed active connector URL.", "Refresh")

    if connector and not bool(runtime.get("auth_required")):
        add("public-auth-disabled", "warning", "Authentication is disabled", "The public connector is active without gateway authentication.", "Review security")

    if stream_state.lower() not in {"live", "replaying"}:
        add("stream-state", "warning", "Activity stream is not live", f"Current stream state: {stream_state or 'offline'}.", "Open logs")

    metrics = dict(health.get("metrics") or {})
    if int(metrics.get("error_count") or 0) > 0:
        add("server-errors", "warning", "Server errors have been recorded", f"{metrics.get('error_count')} 5xx response(s) since process start.", "Run diagnostics")
    if int(metrics.get("auth_failures") or 0) > 0:
        add("auth-failures", "info", "Authentication failures observed", f"{metrics.get('auth_failures')} rejected request(s) since process start.", "Open runtime logs")
    if int(metrics.get("rate_limit_hits") or 0) > 0:
        add("rate-limits", "info", "Rate limiting has activated", f"{metrics.get('rate_limit_hits')} rate-limited request(s) since process start.", "Open runtime logs")

    for check in config_checks or []:
        if check.get("status") == "fail":
            add(f"config-{check.get('name')}", "error", "Configuration validation failed", f"{check.get('name')}: {check.get('message')}", "Open diagnostics")
            break

    rows.sort(key=lambda row: (_SEVERITY_ORDER.get(row["severity"], 9), row["title"]))
    return rows[:8]


def runtime_log_rows(
    repo_root: Path,
    *,
    source: str = "all",
    lines: int = 200,
    query: str = "",
) -> list[dict[str, str]]:
    """Read a bounded snapshot of service logs without turning Center into a terminal."""
    names = list(_RUNTIME_LOG_FILES) if source in {"", "all"} else [source]
    unknown = [name for name in names if name not in _RUNTIME_LOG_FILES]
    if unknown:
        raise ValueError(f"Unknown runtime log source: {unknown[0]}")
    limit = max(0, min(int(lines), 500))
    needle = str(query or "").lower()
    rows: list[dict[str, str]] = []
    for name in names:
        path = Path(repo_root) / "logs" / _RUNTIME_LOG_FILES[name]
        if not path.is_file():
            continue
        window: deque[str] = deque(maxlen=limit)
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    text = raw.rstrip("\r\n")
                    if needle and needle not in text.lower():
                        continue
                    window.append(text)
        except OSError:
            continue
        base = max(0, len(rows))
        for index, text in enumerate(window):
            stamp = ""
            if len(text) >= 19 and text[4:5] == "-" and text[7:8] == "-":
                stamp = text[:26].strip()
            rows.append(
                {
                    "rowId": f"{name}:{base + index}:{hash(text)}",
                    "source": name,
                    "timestamp": stamp,
                    "line": text[:4000],
                }
            )
    return rows[-1000:]


def collect_doctor_snapshot(ctx: Any, *, local_only: bool = False, strict: bool = False) -> dict[str, Any]:
    """Run the same diagnostic primitives as bqa doctor for UI consumption."""
    from app.cli.commands.doctor import (
        _check,
        _executable_check,
        _mcp_check,
        _package_check,
        _process_message,
        _request_check,
    )

    checks: list[dict[str, str]] = []
    repo_root = Path(ctx.repo_root)
    values = dict(getattr(ctx, "values", {}) or {})

    for name, relative in (
        ("virtualenv", ".venv/bin/python"),
        ("fastmcp", ".venv/bin/fastmcp"),
        ("cli_wrapper", "bin/bqa"),
        ("process_helpers", "scripts/process_helpers.sh"),
        ("quality_gate", "scripts/quality_gate.sh"),
    ):
        checks.append(_executable_check(name, repo_root / relative))
    checks.append(_package_check())

    dependencies = check_project_dependencies()
    checks.append(
        _check(
            "project_dependencies",
            "fail" if dependencies["errors"] else "warn" if dependencies["foreign_package_count"] else "pass",
            f"closure of {dependencies['closure_count']} packages · {len(dependencies['errors'])} errors · {dependencies['foreign_package_count']} foreign",
        )
    )
    global_cli = shutil.which("bqa")
    expected_cli = (repo_root / "bin" / "bqa").resolve()
    try:
        global_ok = bool(global_cli) and Path(str(global_cli)).resolve() == expected_cli
    except OSError:
        global_ok = False
    checks.append(_check("global_cli", "pass" if global_ok else "warn", global_cli or "not found in PATH"))
    cloudflared = shutil.which("cloudflared")
    checks.append(_check("cloudflared", "pass" if cloudflared else "warn", cloudflared or "not found"))

    config_checks = validate_config(repo_root, values)
    config_status = "fail" if any(row["status"] == "fail" for row in config_checks) else "warn" if any(row["status"] == "warn" for row in config_checks) else "pass"
    checks.append(_check("config", config_status, f"{len(config_checks)} configuration checks"))

    log_file = resolve_config_path(repo_root, values.get("LOG_FILE", "./logs/gateway.log"))
    try:
        size = log_file.stat().st_size if log_file.exists() else 0
        rotate_at = int(values.get("AUDIT_LOG_MAX_BYTES", "10000000"))
        backups = int(values.get("AUDIT_LOG_BACKUP_COUNT", "5"))
        checks.append(_check("audit_storage", "warn" if size > rotate_at else "pass", f"log size {size} bytes · rotates at {rotate_at} · {backups} backups"))
    except (OSError, ValueError) as exc:
        checks.append(_check("audit_storage", "fail", str(exc)))

    runtime = status_data(repo_root, values)
    checks.extend(
        [
            _check("supervisor", "pass" if runtime["supervisor"]["running"] else "warn", _process_message(runtime["supervisor"])),
            _check("server_process", "pass" if runtime["server"]["running"] else "fail", _process_message(runtime["server"])),
            _check("tunnel_process", "pass" if runtime["tunnel"]["running"] else "warn", _process_message(runtime["tunnel"])),
            _check("bridge_socket", "pass" if runtime["bridge"] == "ready" else "fail", runtime["bridge"]),
        ]
    )

    connect_host = str(values.get("MCP_CONNECT_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    if connect_host in {"0.0.0.0", "::"}:
        connect_host = "127.0.0.1"
    local_base = normalize_base_url(f"http://{connect_host}:{values.get('MCP_PORT', '18427')}")
    local_client = RESTClient(local_base, getattr(ctx, "token", ""), getattr(ctx, "request_timeout", 15.0))
    checks.append(_request_check(local_client, "/healthz", "local_healthz", json_expected=False))
    checks.append(_request_check(local_client, "/api/v1/health", "local_rest"))

    mcp_path = str(values.get("MCP_PATH", "/mcp")).strip() or "/mcp"
    if not mcp_path.startswith("/"):
        mcp_path = f"/{mcp_path}"
    checks.append(_mcp_check(local_client, mcp_path, "local_mcp"))

    if not local_only:
        tunnel_base = canonical_tunnel_base(repo_root)
        if runtime["tunnel"]["running"] and tunnel_base:
            public_client = RESTClient(tunnel_base, getattr(ctx, "token", ""), getattr(ctx, "request_timeout", 15.0))
            checks.append(_request_check(public_client, "/api/v1/health", "public_rest"))
            checks.append(_mcp_check(public_client, mcp_path, "public_mcp"))
            checks.append(
                _check(
                    "public_auth",
                    "pass" if bool_value(values, "REQUIRE_AUTH", False) else "warn",
                    "authentication enabled" if bool_value(values, "REQUIRE_AUTH", False) else "public endpoint has REQUIRE_AUTH=false",
                )
            )
        else:
            checks.append(_check("public_rest", "warn", "tunnel is not running or URL is unavailable"))

    failure_count = sum(row["status"] == "fail" for row in checks)
    warning_count = sum(row["status"] == "warn" for row in checks)
    ok = failure_count == 0 and not (strict and warning_count > 0)
    state = "healthy" if ok and warning_count == 0 else "degraded" if ok else "failed"
    return {
        "ok": ok,
        "status": state,
        "strict": strict,
        "local_only": local_only,
        "warning_count": warning_count,
        "failure_count": failure_count,
        "runtime": runtime,
        "checks": checks,
        "config_checks": config_checks,
    }


def system_snapshot(ctx: Any, *, stream_state: str) -> dict[str, Any]:
    """Cheap periodic snapshot used by the Center refresh worker."""
    repo_root = Path(ctx.repo_root)
    values = dict(getattr(ctx, "values", {}) or {})
    runtime = status_data(repo_root, values)
    health = health_check()
    capabilities = get_capabilities()
    config_checks = validate_config(repo_root, values)
    security = security_posture(values)
    chat_root = resolve_config_path(
        repo_root,
        str(values.get("HOST_CHAT_ROOT") or "~/Downloads/bqa-workspaces"),
    )
    workspaces = workspace_inventory(chat_root)
    return {
        "runtime": runtime,
        "health": health,
        "capabilities": capabilities,
        "config_checks": config_checks,
        "security": security,
        "workspaces": workspaces,
        "workspace_summary": workspace_summary(workspaces),
        "overall": overall_health(runtime, health, stream_state, config_checks),
        "attention": attention_items(runtime, health, stream_state, config_checks),
        "health_metrics": health_metric_rows(health),
    }
