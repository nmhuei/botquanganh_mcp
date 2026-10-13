"""Unified workspace search tool: content search & path globbing.

Consolidates text search and filesystem discovery into an evolved super-tool.
Prefers high-performance ripgrep with safe argv arrays, falls back to optimized
Python traversal, and protects context buffers with payload/line truncation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from app import config
from app.error_contract import ServiceBusyError, format_error_code
from app.host.paths import resolve_host_path
from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.search_models import SearchEngine, SearchLimitReason
from app.search_runtime import default_search_capacity
from app.security import format_error_response
from app.tools_common import (
    _begin_workspace_journal,
    _finish_workspace_journal,
    _guard_chat_id,
    _record_tool_call,
    enforce_bridge_payload_limit,
    fit_json_list_response,
    search_response_budget,
)


def _default_max_matches() -> int:
    try:
        return int(config.WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return int(_defaults["WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES"])


def _max_allowed_matches() -> int:
    try:
        return int(config.WORKSPACE_SEARCH_MAX_RETURNED_MATCHES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return int(_defaults["WORKSPACE_SEARCH_MAX_RETURNED_MATCHES"])


def _max_work_matches() -> int:
    try:
        return int(config.WORKSPACE_SEARCH_MAX_WORK_MATCHES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return int(_defaults["WORKSPACE_SEARCH_MAX_WORK_MATCHES"])


def _bound_response_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the complete tool response below the MCP transport payload limit."""
    from app.tools_common import bridge_payload_ceiling

    try:
        budget = search_response_budget()
    except (ValueError, TypeError, AttributeError):
        budget = bridge_payload_ceiling()
    if "matches" in result and isinstance(result.get("matches"), list):
        fitted = fit_json_list_response(dict(result), "matches", budget)
        # Preserve an existing higher-priority limit reason.
        if result.get("limit_reason") and not fitted.get("limit_reason"):
            fitted["limit_reason"] = result.get("limit_reason")
        elif result.get("limit_reason") and fitted.get("limit_reason") == "payload":
            fitted["limit_reason"] = result.get("limit_reason")
        return fitted
    return result


def _query_digest(query: str | None) -> str:
    raw = str(query or "")
    try:
        key = str(getattr(config, "GATEWAY_TOKEN", "") or "bqa-search-telemetry")
    except (AttributeError, TypeError):
        key = "bqa-search-telemetry"
    return hmac.new(key.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _safe_search_details(
    query: str | None,
    path: str,
    mode: str,
    regex: bool,
    max_matches: int,
    extra: dict[str, Any] | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "query_len": len(str(query or "")),
        "query_digest": _query_digest(query),
        "path": path,
        "mode": mode,
        "regex": regex,
        "max_matches": max_matches,
    }
    if intent:
        details["intent"] = str(intent).strip()[:300]
    if extra:
        details.update(extra)
    return details


def _search_ripgrep(
    root: Path,
    query: str,
    regex: bool,
    case_sensitive: bool,
    max_matches: int,
    include_hidden: bool,
    max_work_matches: int,
    exact_count: bool = False,
    return_count_complete: bool = False,
) -> tuple[list[dict[str, Any]], int] | tuple[list[dict[str, Any]], int, bool]:
    from app import search_engines as engines

    outcome = engines.run_ripgrep_search(
        root, query, regex, case_sensitive, max_matches,
        include_hidden, max_work_matches, exact_count,
    )
    if outcome.ok is False and outcome.error:
        return ([], 0, False) if return_count_complete else ([], 0)
    if return_count_complete:
        return (outcome.matches, outcome.total_found, outcome.count_complete)
    return (outcome.matches, outcome.total_found)


def _search_python(
    root: Path,
    query: str,
    regex: bool,
    case_sensitive: bool,
    max_matches: int,
    include_hidden: bool,
    max_work_matches: int,
    exact_count: bool = False,
    return_count_complete: bool = False,
) -> tuple[list[dict[str, Any]], int] | tuple[list[dict[str, Any]], int, bool]:
    from app import search_engines as engines

    outcome = engines.run_python_search(
        root, query, regex, case_sensitive, max_matches,
        include_hidden, max_work_matches, exact_count,
    )
    if outcome.ok is False and outcome.error:
        return ([], 0, False) if return_count_complete else ([], 0)
    if return_count_complete:
        return (outcome.matches, outcome.total_found, outcome.count_complete)
    return (outcome.matches, outcome.total_found)


def _search_paths_ripgrep(
    root: Path,
    glob_pattern: str,
    include_hidden: bool,
    max_matches: int,
) -> list[str]:
    from app import search_engines as engines

    outcome = engines.run_ripgrep_path_search(
        root, glob_pattern, include_hidden, max_matches,
    )
    return [str(item) for item in outcome.matches]


def _search_paths_python(
    root: Path,
    glob_pattern: str,
    include_hidden: bool,
    max_matches: int,
) -> list[str]:
    """Return bounded file paths by walking only non-ignored directories."""
    from app import search_engines as engines

    outcome = engines.run_python_path_search(
        root, glob_pattern, include_hidden, max_matches,
    )
    return [str(item) for item in outcome.matches]


@mcp.tool(
    name="workspace_search",
    description=(
        "Unified workspace search super-tool. Searches file contents via regex or literal text "
        "(accelerated by ripgrep when available) or glob-matches file paths. "
        "Bind workspace_context before use and pass the bound chat_id. "
        "Enforces context and line-length bounds to protect agent memory. "
        "Requires an attributable chat_id in enforce mode."
    ),
)
def workspace_search(
    query: Optional[str] = None,
    path: str = ".",
    mode: str = "content",
    path_glob: Optional[str] = None,
    regex: bool = False,
    case_sensitive: bool = False,
    include_hidden: bool = False,
    max_matches: Optional[int] = None,
    exact_count: bool = False,
    chat_id: Optional[str] = None,
    intent: Optional[str] = None,
) -> dict[str, Any]:
    """Execute high-speed bounded search across workspace files and contents."""
    validated, rejection = _guard_chat_id("workspace_search", chat_id)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "workspace_search")
    if max_matches is None:
        requested_max = _default_max_matches()
    else:
        try:
            requested_max = int(max_matches)
        except (TypeError, ValueError):
            return enforce_bridge_payload_limit(
                format_error_code("INVALID_ARGUMENT", message="max_matches must be an integer."),
                "workspace_search",
            )
    ceiling = _max_allowed_matches()
    if requested_max < 1 or requested_max > ceiling:
        return enforce_bridge_payload_limit(
            format_error_code(
                "INVALID_ARGUMENT",
                message=f"max_matches must be between 1 and {ceiling}.",
            ),
            "workspace_search",
        )
    bounded_matches = requested_max
    normalized_mode = str(mode or "content").strip().lower()
    if normalized_mode == "auto" or path_glob is not None:
        normalized_mode = "path"
    if normalized_mode not in {"content", "path"}:
        return enforce_bridge_payload_limit(
            format_error_code(
                "INVALID_ARGUMENT",
                message=f"Unknown search mode: {mode}. Expected 'content' or 'path'.",
            ),
            "workspace_search",
        )
    try:
        capacity = default_search_capacity()
    except (ValueError, TypeError, AttributeError):
        capacity = None
    lease = None
    if capacity is not None:
        try:
            lease = capacity.acquire(validated or chat_id)
        except ServiceBusyError as exc:
            busy = format_error_code("SERVICE_BUSY", message=str(exc))
            busy["truncated"] = True
            busy["limit_reason"] = SearchLimitReason.QUEUE.value
            return enforce_bridge_payload_limit(busy, "workspace_search")
    started = time.monotonic()
    engine_started = started
    engine_name = "python"
    journal_details = _safe_search_details(query, path, normalized_mode, regex, bounded_matches, intent=intent)
    journal_op = _begin_workspace_journal("workspace_search", validated, journal_details)
    result: dict[str, Any] = {}
    outcome_counters: dict[str, Any] = {}
    limit_value: str | None = None
    error_class: str | None = None
    try:
        resolved = resolve_host_path(path)
        if normalized_mode == "path":
            from app import search_engines as engines

            engine_started = time.monotonic()
            glob_pattern = path_glob if path_glob is not None else query or "*"
            has_rg = bool(shutil.which("rg"))
            if has_rg:
                path_outcome = engines.run_ripgrep_path_search(
                    resolved, glob_pattern, include_hidden, bounded_matches,
                )
            else:
                path_outcome = engines.run_python_path_search(
                    resolved, glob_pattern, include_hidden, bounded_matches,
                )
            engine_name = (
                path_outcome.engine.value
                if isinstance(path_outcome.engine, SearchEngine)
                else str(path_outcome.engine)
            )
            path_reason = (
                path_outcome.limit_reason.value if path_outcome.limit_reason else None
            )
            limit_value = path_reason
            result = {
                "ok": True,
                "mode": "path",
                "pattern": glob_pattern,
                "engine": engine_name,
                "total_matches_found": path_outcome.total_found,
                "matches": list(path_outcome.matches),
                "truncated": bool(path_outcome.limit_reason is not None),
                "returned_matches": len(path_outcome.matches),
                "count_complete": bool(path_outcome.count_complete),
                "scanned_files": path_outcome.counters.scanned_files,
                "scanned_bytes": path_outcome.counters.scanned_bytes,
            }
            if path_reason:
                result["limit_reason"] = path_reason
            engine_duration = (time.monotonic() - engine_started) * 1000
            payload_started = time.monotonic()
            result = _bound_response_payload(result)
            if result.get("truncated") and result.get("limit_reason") is None:
                result["limit_reason"] = SearchLimitReason.PAYLOAD.value
                limit_value = result["limit_reason"]
            payload_duration = (time.monotonic() - payload_started) * 1000
            outcome_counters = {
                "scanned_files": path_outcome.counters.scanned_files,
                "scanned_bytes": path_outcome.counters.scanned_bytes,
                "candidate_matches": path_outcome.total_found,
                "returned_matches": len(result.get("matches", [])),
            }
        else:
            if not query:
                result = {
                    "ok": False,
                    "error": {
                        "code": "MISSING_QUERY",
                        "message": "Content search requires a non-empty 'query' string.",
                    },
                }
                return enforce_bridge_payload_limit(result, "workspace_search")
            from app import search_engines as engines

            has_rg = bool(shutil.which("rg"))
            work_budget = _max_work_matches()
            engine_started = time.monotonic()
            try:
                if has_rg:
                    outcome = engines.run_ripgrep_search(
                        resolved, query=query, regex=regex,
                        case_sensitive=case_sensitive, max_matches=bounded_matches,
                        include_hidden=include_hidden, max_work_matches=work_budget,
                        exact_count=exact_count,
                    )
                else:
                    outcome = engines.run_python_search(
                        resolved, query=query, regex=regex,
                        case_sensitive=case_sensitive, max_matches=bounded_matches,
                        include_hidden=include_hidden, max_work_matches=work_budget,
                        exact_count=exact_count,
                    )
            except (ValueError, TypeError, OSError) as exc:
                error_class = type(exc).__name__
                result = format_error_response(exc)
                raise
            engine_duration = (time.monotonic() - engine_started) * 1000
            engine_name = outcome.engine.value if isinstance(outcome.engine, SearchEngine) else str(outcome.engine)
            if outcome.ok is False:
                error_class = str((outcome.error or {}).get("code") or "ENGINE_ERROR")
                code = str((outcome.error or {}).get("code") or "INTERNAL_ERROR")
                message = str((outcome.error or {}).get("message") or "Search engine failed.")
                result = format_error_code(code, message=message)
                result["engine"] = engine_name
            else:
                reason = outcome.limit_reason.value if outcome.limit_reason else None
                truncated = (outcome.total_found > len(outcome.matches)) or (not outcome.count_complete)
                if truncated and reason is None and outcome.total_found > len(outcome.matches):
                    reason = SearchLimitReason.RESULT_CAP.value
                limit_value = reason
                payload_started = time.monotonic()
                candidate = {
                    "ok": True,
                    "mode": "content",
                    "regex": regex,
                    "engine": engine_name,
                    "total_matches_found": outcome.total_found,
                    "count_complete": outcome.count_complete,
                    "total_matches_is_partial": not outcome.count_complete,
                    "returned_matches": len(outcome.matches),
                    "truncated": bool(truncated),
                    "matches": list(outcome.matches),
                    "scanned_files": outcome.counters.scanned_files,
                    "scanned_bytes": outcome.counters.scanned_bytes,
                }
                if reason:
                    candidate["limit_reason"] = reason
                budget = search_response_budget()
                fitted = fit_json_list_response(candidate, "matches", budget)
                if fitted.get("truncated") and fitted.get("limit_reason") is None:
                    fitted["limit_reason"] = SearchLimitReason.PAYLOAD.value
                # Preserve engine priority over payload fitting.
                if reason and fitted.get("limit_reason") == SearchLimitReason.PAYLOAD.value:
                    fitted["limit_reason"] = reason
                if fitted.get("limit_reason"):
                    limit_value = str(fitted.get("limit_reason"))
                result = fitted
                outcome_counters = {
                    "scanned_files": outcome.counters.scanned_files,
                    "scanned_bytes": outcome.counters.scanned_bytes,
                    "candidate_matches": outcome.total_found,
                    "returned_matches": len(fitted.get("matches", [])),
                }
                payload_duration = (time.monotonic() - payload_started) * 1000
    except Exception as exc:
        error_class = error_class or type(exc).__name__
        if not result:
            result = format_error_response(exc)
    finally:
        total_duration = (time.monotonic() - started) * 1000
        try:
            response_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            response_bytes = 0
        safe_telemetry = {
            "engine": engine_name,
            "mode": normalized_mode,
            "duration_ms": round(total_duration, 1),
            "engine_duration_ms": round(engine_duration if "engine_duration" in dir() else 0.0, 1),
            "payload_duration_ms": round(payload_duration if "payload_duration" in dir() else 0.0, 1),
            "returned_matches": len(result.get("matches", [])) if isinstance(result.get("matches"), list) else 0,
            "response_bytes": response_bytes,
            "truncated": bool(result.get("truncated", False)),
            "limit_reason": limit_value or result.get("limit_reason"),
            "error_class": error_class,
            **{f"counter_{k}": v for k, v in outcome_counters.items()},
            **_safe_search_details(query, path, normalized_mode, regex, bounded_matches, intent=intent),
        }
        # Never include raw query or match text in telemetry.
        safe_telemetry.pop("query", None)
        try:
            log_audit_event("WORKSPACE_SEARCH_COMPLETED", safe_telemetry)
        except (OSError, ValueError, TypeError):
            pass
        if lease is not None:
            try:
                lease.release()
            except (AttributeError, ValueError, RuntimeError):
                pass
        _finish_workspace_journal(
            "workspace_search", validated, journal_op,
            ok=isinstance(result, dict) and bool(result.get("ok", False)),
            details=safe_telemetry,
        )
    result = _bound_response_payload(result)
    _record_tool_call("workspace_search", validated)
    return enforce_bridge_payload_limit(result, "workspace_search")
