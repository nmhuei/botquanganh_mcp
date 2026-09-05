from datetime import datetime, timezone

from app.config import (
    HOST_COMMAND_POLICY,
    HOST_KNOWLEDGE_DIR,
    HOST_RESTRICT_TO_WORKSPACE,
    HOST_WORKSPACE_DIR,
    COMMAND_QUEUE_TIMEOUT_SECONDS,
    MAX_CONCURRENT_COMMANDS,
    MAX_OUTPUT_BYTES,
    MAX_SINGLE_FILE_BYTES,
    MAX_TIMEOUT_SECONDS,
    SERVICE_NAME,
    VERSION,
)
from app.host.executor import command_capacity
from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.metrics import metrics
from app.observability import transport_observability
from app.security import format_error_response

HOST_TOOLS = [
    "host_list_directory",
    "host_read_file",
    "host_write_file",
    "host_replace_in_file",
    "host_append_file",
    "host_make_directory",
    "host_search_text",
    "host_check_command",
    "host_run_command",
    "ctf_fetch_url",
    "ctf_render_fetch_result",
    "ctf_triage_artifact",
    "host_knowledge",
    "host_workspace_bind",
    "host_save_note",
]


@mcp.tool(name="health_check", description="Verify that the host MCP server is reachable.")
def health_check() -> dict:
    try:
        stats = metrics.get_stats()
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "version": VERSION,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "profile": "host",
            "workspace": str(HOST_WORKSPACE_DIR),
            "command_policy": HOST_COMMAND_POLICY,
            "metrics": {
                "uptime_seconds": stats["uptime_seconds"],
                "total_requests": stats["total_requests"],
                "mcp_http_requests_total": stats["mcp_http_requests_total"],
                "error_count": stats["error_count"],
                "client_error_count": stats["client_error_count"],
                "auth_failures": stats["auth_failures"],
                "rate_limit_hits": stats["rate_limit_hits"],
                "in_flight": stats["in_flight"],
                "peak_in_flight": stats["peak_in_flight"],
                "avg_latency_ms": stats["avg_latency_ms"],
                "p50_latency_ms": stats["p50_latency_ms"],
                "p95_latency_ms": stats["p95_latency_ms"],
                "p99_latency_ms": stats["p99_latency_ms"],
                "response_bytes": stats["response_bytes"],
                "mcp_response_bytes": stats["mcp_response_bytes"],
                "avg_response_bytes": stats["avg_response_bytes"],
                "incomplete_responses": stats["incomplete_responses"],
                "client_disconnects": stats["client_disconnects"],
                "status_counts": stats["status_counts"],
                "latency_sample_size": stats["latency_sample_size"],
            },
            "capacity": {
                "commands": command_capacity.get_stats(),
            },
            "transport": transport_observability.snapshot(),
        }
    except Exception as exc:
        log_audit_event("HEALTH_CHECK_FAIL", {"error": str(exc)})
        return format_error_response(exc)


@mcp.tool(
    name="get_capabilities",
    description="List the host MCP tools, workspace policy, knowledge source, and limits.",
)
def get_capabilities() -> dict:
    try:
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "version": VERSION,
            "profile": "host",
            "tools": [
                "health_check",
                "get_capabilities",
                *HOST_TOOLS,
            ],
            "host": {
                "workspace": str(HOST_WORKSPACE_DIR),
                "restrict_to_workspace": HOST_RESTRICT_TO_WORKSPACE,
                "command_policy": HOST_COMMAND_POLICY,
                "knowledge_dir": str(HOST_KNOWLEDGE_DIR),
                "caller_approval_parameter": False,
            },
            "limits": {
                "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
                "max_single_file_bytes": MAX_SINGLE_FILE_BYTES,
                "max_output_bytes": MAX_OUTPUT_BYTES,
                "max_concurrent_commands": MAX_CONCURRENT_COMMANDS,
                "command_queue_timeout_seconds": COMMAND_QUEUE_TIMEOUT_SECONDS,
            },
            "features": {
                "host_filesystem": True,
                "host_command_execution": True,
                "host_knowledge": True,
                "ctf_fetch_result_ui": True,
                "installed_tool_inventory": True,
            },
        }
    except Exception as exc:
        log_audit_event("GET_CAPABILITIES_FAIL", {"error": str(exc)})
        return format_error_response(exc)
