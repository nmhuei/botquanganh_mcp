from __future__ import annotations

import os
import re
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from app.cli.client import RESTClient
from app.cli.config_view import bool_value, resolve_config_path, validate_config
from app.cli.context import CLIContext, normalize_base_url
from app.cli.lifecycle import canonical_tunnel_base, status_data
from app.cli.output import (
    COMPACT_WIDTH,
    CONTINUATION_INDENT,
    INDENT,
    LABEL_GAP,
    emit_json,
    emit_quiet,
    renderer_for,
    style,
    visible_width,
)
from app.cli.progress import progress_for
from app.dependency_check import check_project_dependencies


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _process_message(process: dict) -> str:
    if process.get("running"):
        pid = process.get("pid")
        return f"running · pid {pid}" if pid else "running"
    return "stopped"


def _request_check(
    client: RESTClient,
    path: str,
    name: str,
    *,
    json_expected: bool = True,
) -> dict[str, str]:
    try:
        result = client.raw_request("GET", path)
        if result.status != 200:
            return _check(name, "fail", f"HTTP {result.status}")
        if json_expected:
            payload = result.json()
            if not isinstance(payload, dict) or not payload.get("ok", False):
                return _check(name, "fail", "response is not healthy")
        return _check(name, "pass", f"HTTP {result.status}")
    except Exception as exc:
        return _check(name, "fail", str(exc))


def _mcp_check(client: RESTClient, path: str, name: str) -> dict[str, str]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "bqa-doctor", "version": "1.0"},
        },
    }
    try:
        result = client.raw_request(
            "POST",
            path,
            json_body=payload,
            accept="application/json, text/event-stream",
        )
        if result.status != 200:
            return _check(name, "fail", f"HTTP {result.status}")
        body = result.json()
        if not isinstance(body, dict) or "result" not in body:
            return _check(name, "fail", "initialize result missing")
        return _check(name, "pass", "initialize succeeded")
    except Exception as exc:
        return _check(name, "fail", str(exc))


def _executable_check(name: str, path: Path) -> dict[str, str]:
    valid = path.is_file() and os.access(path, os.X_OK)
    return _check(name, "pass" if valid else "fail", str(path))


def _package_check() -> dict[str, str]:
    try:
        installed = version("botquanganh-host-mcp")
    except PackageNotFoundError:
        return _check("editable_package", "fail", "package metadata not installed")
    return _check("editable_package", "pass", installed)


_URL_RE = re.compile(r"https?://\S+")


def _split_copyable_rows(
    renderer: Any,
    checks: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    """Split diagnostics into table rows and own-line copyable entries.

    Messages that embed a URL (for example connection failures carrying the
    connector URL) or that exceed the inline value width are lifted out of
    the STATE/CHECK/DETAIL grid: the table row shows a short pointer while
    the full message is emitted below through ``Renderer.copyable_value``,
    so the connector URL stays untruncated and unsplit at every width.
    """
    columns = renderer.columns
    if columns < COMPACT_WIDTH:
        inline_limit = max(10, columns - CONTINUATION_INDENT)
    else:
        label_width = max(
            (visible_width(str(item.get("name", ""))) for item in checks),
            default=0,
        )
        inline_limit = max(10, columns - INDENT - label_width - LABEL_GAP)
    table_rows: list[dict[str, str]] = []
    copyable_rows: list[tuple[str, str]] = []
    for check in checks:
        message = str(check.get("message", ""))
        over_budget = visible_width(message) > inline_limit
        if _URL_RE.search(message) or over_budget:
            copyable_rows.append((str(check.get("name", "")), message))
            table_rows.append({**check, "message": "see below"})
        else:
            table_rows.append(check)
    return table_rows, copyable_rows


def handle_doctor(ctx: CLIContext, args) -> int:
    checks: list[dict[str, str]] = []
    strict = bool(getattr(args, "strict", False))
    local_only = bool(getattr(args, "local_only", False))

    doctor_rows = [
        "local tooling",
        "configuration",
        "audit storage",
        "managed runtime",
        "local REST",
        "local MCP",
    ]
    if not local_only:
        doctor_rows.append("public connector")
    doctor_rows.append("diagnostics")

    with progress_for(
        ctx,
        "Checking system...",
        total=len(doctor_rows),
    ) as progress:
        progress.set_items(doctor_rows)
        checks.append(
            _executable_check("virtualenv", ctx.repo_root / ".venv" / "bin" / "python")
        )
        checks.append(
            _executable_check("fastmcp", ctx.repo_root / ".venv" / "bin" / "fastmcp")
        )
        checks.append(_executable_check("cli_wrapper", ctx.repo_root / "bin" / "bqa"))
        checks.append(
            _executable_check(
                "process_helpers",
                ctx.repo_root / "scripts" / "process_helpers.sh",
            )
        )
        checks.append(
            _executable_check(
                "quality_gate",
                ctx.repo_root / "scripts" / "quality_gate.sh",
            )
        )
        checks.append(_package_check())
        dependency_result = check_project_dependencies()
        dependency_status = (
            "fail"
            if dependency_result["errors"]
            else "warn"
            if dependency_result["foreign_package_count"] > 0
            else "pass"
        )
        checks.append(
            _check(
                "project_dependencies",
                dependency_status,
                (
                    f"closure of {dependency_result['closure_count']} packages · "
                    f"{len(dependency_result['errors'])} errors · "
                    f"{dependency_result['foreign_package_count']} foreign"
                ),
            )
        )

        global_cli = shutil.which("bqa")
        expected_cli = (ctx.repo_root / "bin" / "bqa").resolve()
        global_ok = False
        if global_cli:
            try:
                global_ok = Path(global_cli).resolve() == expected_cli
            except OSError:
                global_ok = False
        checks.append(
            _check(
                "global_cli",
                "pass" if global_ok else "warn",
                global_cli or "not found in PATH",
            )
        )

        cloudflared = shutil.which("cloudflared")
        checks.append(
            _check(
                "cloudflared",
                "pass" if cloudflared else "warn",
                cloudflared or "not found",
            )
        )
        progress.complete_item("local tooling")

        config_checks = validate_config(ctx.repo_root, ctx.values)
        config_status = (
            "fail"
            if any(item["status"] == "fail" for item in config_checks)
            else "warn"
            if any(item["status"] == "warn" for item in config_checks)
            else "pass"
        )
        checks.append(
            _check("config", config_status, f"{len(config_checks)} configuration checks")
        )
        progress.complete_item("configuration")

        log_file = resolve_config_path(
            ctx.repo_root,
            ctx.values.get("LOG_FILE", "./logs/gateway.log"),
        )
        try:
            size = log_file.stat().st_size if log_file.exists() else 0
            rotate_at = int(ctx.values.get("AUDIT_LOG_MAX_BYTES", "10000000"))
            backups = int(ctx.values.get("AUDIT_LOG_BACKUP_COUNT", "5"))
            checks.append(
                _check(
                    "audit_storage",
                    "warn" if size > rotate_at else "pass",
                    f"log size {size} bytes · rotates at {rotate_at} · {backups} backups",
                )
            )
        except (OSError, ValueError) as exc:
            checks.append(_check("audit_storage", "fail", str(exc)))
        progress.complete_item("audit storage")

        runtime = status_data(ctx.repo_root, ctx.values)
        checks.append(
            _check(
                "supervisor",
                "pass" if runtime["supervisor"]["running"] else "warn",
                _process_message(runtime["supervisor"]),
            )
        )
        checks.append(
            _check(
                "server_process",
                "pass" if runtime["server"]["running"] else "fail",
                _process_message(runtime["server"]),
            )
        )
        checks.append(
            _check(
                "tunnel_process",
                "pass" if runtime["tunnel"]["running"] else "warn",
                _process_message(runtime["tunnel"]),
            )
        )
        checks.append(
            _check(
                "bridge_socket",
                "pass" if runtime["bridge"] == "ready" else "fail",
                runtime["bridge"],
            )
        )
        progress.complete_item("managed runtime")

        connect_host = (
            ctx.values.get("MCP_CONNECT_HOST", "127.0.0.1").strip() or "127.0.0.1"
        )
        if connect_host in {"0.0.0.0", "::"}:  # nosec B104
            connect_host = "127.0.0.1"
        local_base = normalize_base_url(
            f"http://{connect_host}:{ctx.values.get('MCP_PORT', '18427')}"
        )
        local_client = RESTClient(local_base, ctx.token, ctx.request_timeout)
        checks.append(
            _request_check(local_client, "/healthz", "local_healthz", json_expected=False)
        )
        checks.append(_request_check(local_client, "/api/v1/health", "local_rest"))
        progress.complete_item("local REST")

        mcp_path = ctx.values.get("MCP_PATH", "/mcp").strip() or "/mcp"
        if not mcp_path.startswith("/"):
            mcp_path = f"/{mcp_path}"
        checks.append(_mcp_check(local_client, mcp_path, "local_mcp"))
        progress.complete_item("local MCP")

        if not local_only:
            tunnel_base = canonical_tunnel_base(ctx.repo_root)
            if runtime["tunnel"]["running"] and tunnel_base:
                public_client = RESTClient(tunnel_base, ctx.token, ctx.request_timeout)
                checks.append(
                    _request_check(public_client, "/api/v1/health", "public_rest")
                )
                checks.append(_mcp_check(public_client, mcp_path, "public_mcp"))
                if not bool_value(ctx.values, "REQUIRE_AUTH", False):
                    checks.append(
                        _check(
                            "public_auth",
                            "warn",
                            "public endpoint has REQUIRE_AUTH=false",
                        )
                    )
                else:
                    checks.append(_check("public_auth", "pass", "authentication enabled"))
            else:
                checks.append(
                    _check(
                        "public_rest",
                        "warn",
                        "tunnel is not running or URL is unavailable",
                    )
                )

        if not local_only:
            progress.complete_item("public connector")

        failure_count = sum(item["status"] == "fail" for item in checks)
        warning_count = sum(item["status"] == "warn" for item in checks)
        ok = failure_count == 0 and not (strict and warning_count > 0)
        state = "healthy" if ok and warning_count == 0 else "degraded" if ok else "failed"
        payload = {
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
        progress.complete_item("diagnostics")
        progress.finish(f"Checked {len(checks)} diagnostics")

    if ctx.json_output:
        emit_json(payload)
    elif ctx.quiet:
        emit_quiet(state)
    else:
        renderer = renderer_for(ctx)
        renderer.header(
            "System doctor",
            "Local diagnostics" if local_only else "Local and public diagnostics",
        )
        renderer.blank()
        renderer.status(state)
        renderer.blank()
        table_checks, copyable_rows = _split_copyable_rows(renderer, checks)
        renderer.checks(table_checks)
        if copyable_rows:
            renderer.blank()
            for row_name, row_message in copyable_rows:
                renderer.copyable_value(row_name, row_message)
        renderer.blank()
        renderer.summary(
            "   ".join(
                (
                    style(
                        f"{len(checks) - warning_count - failure_count} passed",
                        "green",
                        color_mode=renderer.color_mode,
                        stream=renderer.stream,
                    ),
                    style(
                        f"{warning_count} warnings",
                        "yellow",
                        color_mode=renderer.color_mode,
                        stream=renderer.stream,
                    ),
                    style(
                        f"{failure_count} failed",
                        "red",
                        color_mode=renderer.color_mode,
                        stream=renderer.stream,
                    ),
                )
            ),
            "success"
            if state == "healthy"
            else "warn"
            if state == "degraded"
            else "error",
        )
        if warning_count or failure_count:
            renderer.blank()
            renderer.hint("bqa config validate", "Review configuration with")
    return 0 if ok else 1
