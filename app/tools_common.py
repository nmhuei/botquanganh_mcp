"""Common attribution, journaling, and safety guards for BQA MCP 2.0 Super-Tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from app.chat_identity import InvalidChatId, validate_chat_id
from app.error_contract import format_error_code
from app.logging_audit import (
    effective_attribution_mode,
    log_audit_event,
    stamp_chat_id,
)


def bridge_payload_ceiling() -> int:
    """Return the canonical MCP response ceiling from configuration."""
    try:
        from app import config as config_module

        return int(config_module.MCP_MAX_PAYLOAD_BYTES)
    except (AttributeError, TypeError, ValueError):
        from app.cli.config_view import DEFAULTS as _defaults

        return int(_defaults["MCP_MAX_PAYLOAD_BYTES"])


def bridge_overhead_bytes() -> int:
    """Return reserved envelope bytes from configuration."""
    try:
        from app import config as config_module

        return max(0, int(config_module.MCP_TOOL_RESULT_OVERHEAD_BYTES))
    except (AttributeError, TypeError, ValueError):
        return 0


def search_response_budget() -> int:
    """Return bounded search budget strictly within ceiling minus overhead.

    No minimum floor applies. The budget never exceeds the configured
    ceiling minus reserved overhead so the final envelope fits.
    """
    try:
        from app import config as config_module

        ceiling = int(config_module.MCP_MAX_PAYLOAD_BYTES)
        reserved = int(config_module.MCP_TOOL_RESULT_OVERHEAD_BYTES)
    except (AttributeError, TypeError, ValueError):
        ceiling = bridge_payload_ceiling()
        reserved = bridge_overhead_bytes()
    return max(0, ceiling - max(0, reserved))


def fit_json_list_response(
    envelope: dict[str, Any], list_key: str, budget_bytes: int
) -> dict[str, Any]:
    """Keep the longest ordered prefix of a list field within a byte budget.

    Each item is serialized exactly once. List separators use two bytes
    (comma plus space) to match default json.dumps output. One byte of
    safety covers false versus true growth. One final serialization
    verifies the result. A compact empty response applies when the base
    envelope cannot fit.
    """
    items = envelope.get(list_key)
    if not isinstance(items, list):
        return dict(envelope)
    budget = int(budget_bytes)
    item_bytes: list[bytes] = []
    for item in items:
        try:
            item_bytes.append(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            item_bytes.append(b"null")
    has_returned = "returned_matches" in envelope
    reason = envelope.get("limit_reason") or "payload"
    template = dict(envelope)
    template[list_key] = []
    template["truncated"] = True
    template["limit_reason"] = reason
    if has_returned:
        template["returned_matches"] = len(items)
    try:
        base_bytes = len(json.dumps(template, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return dict(envelope)
    if base_bytes > budget:
        minimal: dict[str, Any] = {
            "ok": envelope.get("ok", True),
            list_key: [],
            "truncated": True,
            "limit_reason": "payload",
        }
        if has_returned:
            minimal["returned_matches"] = 0
        try:
            if len(json.dumps(minimal, ensure_ascii=False).encode("utf-8")) <= budget:
                return minimal
        except (TypeError, ValueError):
            pass
        return minimal
    available = budget - base_bytes
    kept = 0
    used = 0
    for index, raw in enumerate(item_bytes):
        need = len(raw) + (2 if kept > 0 else 0)
        if used + need > available:
            break
        used += need
        kept = index + 1
    payload_truncated = kept < len(items)
    result = dict(envelope)
    result[list_key] = items[:kept]
    if payload_truncated:
        result["truncated"] = True
        if result.get("limit_reason") is None:
            result["limit_reason"] = "payload"
    if has_returned:
        result["returned_matches"] = kept
    try:
        final_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return result
    if final_bytes <= budget:
        return result
    estimate = used
    target = kept
    for idx in range(kept - 1, -1, -1):
        growth = 1 if (target == len(items) and envelope.get("truncated") is False) else 0
        if base_bytes + estimate + growth <= budget:
            break
        estimate -= len(item_bytes[idx]) + (2 if idx > 0 else 0)
        target = idx
    result[list_key] = items[:target]
    if target < len(items):
        result["truncated"] = True
        if result.get("limit_reason") is None:
            result["limit_reason"] = "payload"
    if has_returned:
        result["returned_matches"] = target
    try:
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= budget:
            return result
    except (TypeError, ValueError):
        return result
    minimal: dict[str, Any] = {
        "ok": envelope.get("ok", True),
        list_key: [],
        "truncated": True,
        "limit_reason": "payload",
    }
    if has_returned:
        minimal["returned_matches"] = 0
    return minimal


def enforce_payload(data: Any, max_bytes: int | None = None) -> Any:
    """Enforce strict wire ceiling on tool response data.

    Raises ValueError if serialized payload exceeds max_bytes.
    """
    ceiling = int(max_bytes) if max_bytes is not None else bridge_payload_ceiling()
    if isinstance(data, (bytes, bytearray)):
        raw_len = len(data)
    elif isinstance(data, str):
        raw_len = len(data.encode("utf-8", errors="replace"))
    else:
        raw_len = len(json.dumps(data, ensure_ascii=False).encode("utf-8", errors="replace"))
    if raw_len > ceiling:
        raise ValueError(f"Payload ({raw_len} bytes) exceeds wire limit ({ceiling} bytes).")
    return data


def _serialized_byte_len(payload: dict[str, Any]) -> int:
    """Return UTF-8 byte length of a JSON payload."""
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _bridge_base_error(tool_name: str, encoded_len: int, ceiling: int) -> dict[str, Any]:
    """Build a dynamic bridge-limit error without hardcoded ceilings."""
    return {
        "ok": False,
        "truncated": True,
        "error": {
            "code": "PAYLOAD_LIMIT_EXCEEDED",
            "name": "OUTPUT_EXCEEDS_BRIDGE_LIMIT",
            "message": (
                f'Output for tool "{tool_name}" ({encoded_len} bytes) exceeded '
                f"the bridge payload ceiling ({ceiling} bytes)."
            ),
            "suggestion": (
                f"Apply filters or pagination to bound payload below {ceiling} bytes."
            ),
            "recommendations": [
                "Pipe terminal output through filters or redirect to a file.",
                "Read files with small line windows instead of full reads.",
                "Use specific queries and reduce max_matches for search.",
            ],
        },
        "original_bytes": encoded_len,
        "limit_bytes": ceiling,
        "preview": None,
    }


def _drop_bridge_recommendations(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove verbose hints when the error envelope itself is oversized."""
    error = dict(payload.get("error") or {})
    error.pop("recommendations", None)
    error["suggestion"] = "Reduce output size and retry."
    payload = dict(payload)
    payload["error"] = error
    return payload


def _fit_bridge_preview(
    base: dict[str, Any], serialized: str, ceiling: int
) -> dict[str, Any]:
    """Attach the longest preview prefix that keeps the envelope in budget."""
    try:
        base_len = _serialized_byte_len(base)
    except (TypeError, ValueError):
        base["preview"] = None
        return base
    allowance = max(0, ceiling - base_len)
    preview = serialized[:allowance] or None
    candidate = dict(base)
    candidate["preview"] = preview
    try:
        while preview and _serialized_byte_len(candidate) > ceiling:
            preview = preview[: len(preview) // 2] or None
            candidate["preview"] = preview
            if not preview:
                break
    except (TypeError, ValueError):
        candidate["preview"] = None
    return candidate


def _shrink_bridge_error(payload: dict[str, Any], ceiling: int) -> dict[str, Any]:
    """Shrink an oversized error envelope until it fits the ceiling."""
    current = dict(payload)
    try:
        if _serialized_byte_len(current) <= ceiling:
            return current
    except (TypeError, ValueError):
        return current
    current = _drop_bridge_recommendations(current)
    try:
        if _serialized_byte_len(current) <= ceiling:
            return current
    except (TypeError, ValueError):
        return current
    error = dict(current.get("error") or {})
    error["message"] = "Output exceeded bridge payload ceiling."
    error["suggestion"] = "Reduce output size and retry."
    current["error"] = error
    try:
        if _serialized_byte_len(current) <= ceiling:
            return current
    except (TypeError, ValueError):
        return current
    current["preview"] = None
    return current


def enforce_bridge_payload_limit(
    payload: dict[str, Any],
    tool_name: str = "tool",
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Return an error when the serialized payload exceeds the bridge limit."""
    ceiling = int(max_bytes) if max_bytes is not None else bridge_payload_ceiling()
    serialized = json.dumps(payload, ensure_ascii=False)
    encoded_len = len(serialized.encode("utf-8"))
    if encoded_len <= ceiling:
        return payload
    base = _bridge_base_error(tool_name, encoded_len, ceiling)
    fitted = _fit_bridge_preview(base, serialized, ceiling)
    return _shrink_bridge_error(fitted, ceiling)


BIND_EXEMPT_TOOLS = frozenset({"server_info"})


def is_prebind_allowed(tool: str, action: Optional[str] = None) -> bool:
    """Return True if (tool, action) is permitted prior to workspace binding.

    Pre-bind allowed operations:
    1. server_info
    2. workspace_context(action="bind")
    3. workspace_context(action="list")
    """
    if tool == "server_info":
        return True
    if tool == "workspace_context":
        norm_action = (action or "bind").strip().lower()
        return norm_action in {"bind", "list"}
    return False


def _invalid_chat_id_payload() -> dict[str, Any]:
    try:
        from app.chat_errors import ChatCatalogError, to_tool_error

        return to_tool_error(ChatCatalogError("E1"))
    except ImportError:
        return {
            "ok": False,
            "error": {
                "code": "E1",
                "name": "INVALID_CHAT_ID",
                "message": "Supplied chat id is malformed.",
                "suggestion": "Pass a valid chat id matching 6..64 chars alphanumeric.",
            },
        }


def _bind_required_payload(tool: str) -> dict[str, Any]:
    payload: Optional[dict[str, Any]] = None
    try:
        from app.chat_errors import CHAT_ERROR_CATALOG, chat_error_payload

        if "E6" in CHAT_ERROR_CATALOG:
            payload = chat_error_payload("E6")
    except ImportError:
        payload = None
    if payload is None:
        payload = {
            "ok": False,
            "error": {
                "code": "E6",
                "name": "BIND_REQUIRED",
                "message": (
                    f"{tool} requires a bound chat id while ATTRIBUTION_MODE=enforce."
                ),
                "suggestion": (
                    "Call workspace_context with action='bind' first, then "
                    "pass that chat_id to subsequent tool calls."
                ),
            },
        }
    error = payload.get("error")
    if isinstance(error, dict):
        error["instructions"] = [
            "1. Call 'workspace_context(action=\"list\")' to view previous workspaces.",
            "2. Call 'workspace_context(action=\"bind\", resume_id=\"latest\")' to resume, or 'workspace_context(action=\"bind\")' for a new workspace.",
            "3. After binding, pass the returned chat_id to subsequent operations.",
        ]
    return payload


def _is_enforcing_mode() -> bool:
    try:
        from app.chat_identity import is_enforcing

        return bool(is_enforcing())
    except ImportError:
        pass
    from app import config as config_module

    raw = str(getattr(config_module, "ATTRIBUTION_MODE", "") or "").strip().lower()
    return raw == "enforce"


def _context_chat_id() -> Optional[str]:
    try:
        from app.chat_identity import get_chat_id

        candidate = get_chat_id()
        if candidate is not None:
            return validate_chat_id(candidate)
    except (ImportError, InvalidChatId):
        pass
    return None


def _guard_chat_id(
    tool: str, chat_id: Optional[str], action: Optional[str] = None
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Validate caller chat id and enforce Level 4 attribution.

    Checks capability against pre-bind allowlist and binding registry.
    """
    resolved = chat_id
    exempt = is_prebind_allowed(tool, action)

    if (resolved is None or not resolved) and _is_enforcing_mode():
        if exempt:
            return None, None
        resolved = _context_chat_id()
        if resolved is None or not resolved:
            return None, _bind_required_payload(tool)

    if resolved is None or not resolved:
        if exempt:
            return None, None
        if effective_attribution_mode() == "strict":
            return None, format_error_code(
                "INVALID_ARGUMENT",
                message=f"{tool} requires chat_id while ATTRIBUTION_MODE=strict",
            )
        return None, None

    try:
        validated = validate_chat_id(resolved)
    except InvalidChatId:
        return None, _invalid_chat_id_payload()

    if _is_enforcing_mode() and not exempt:
        from app import config as config_module
        from app.workspace_binding import validate_workspace_binding

        if not getattr(config_module, "HOST_CHAT_WORKSPACES", False):
            return None, _bind_required_payload(tool)

        root_str = getattr(config_module, "HOST_CHAT_ROOT", "")
        if not root_str:
            return None, _bind_required_payload(tool)

        root = Path(root_str).expanduser().resolve()
        if not validate_workspace_binding(root, validated):
            return None, _bind_required_payload(tool)

    return validated, None


def _guard_operation(
    tool: str, chat_id: Optional[str] = None, *, action: Optional[str] = None
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Convenience alias for operation-aware attribution guard."""
    return _guard_chat_id(tool, chat_id, action=action)


def _stamp_chat_id(
    details: dict[str, Any], chat_id: Optional[str]
) -> dict[str, Any]:
    if chat_id and _is_enforcing_mode():
        details["chat_id"] = chat_id
        return details
    return stamp_chat_id(details, chat_id)


def _record_tool_call(
    tool: str,
    chat_id: Optional[str],
    details: Optional[dict[str, Any]] = None,
    ok: bool = True,
) -> None:
    payload = {
        key: value for key, value in (details or {}).items() if value is not None
    }
    _stamp_chat_id(payload, chat_id)
    payload["ok"] = ok
    if payload:
        log_audit_event("HOST_TOOL_CALL", {"tool": tool, **payload})


def _journal_error(tool: str, chat_id: str, phase: str, exc: Exception) -> None:
    log_audit_event(
        "WORKSPACE_JOURNAL_ERROR",
        {
            "tool": tool,
            "chat_id": chat_id,
            "phase": phase,
            "error_type": type(exc).__name__,
        },
    )


def _begin_workspace_journal(
    tool: str,
    chat_id: Optional[str],
    details: Optional[dict[str, Any]] = None,
) -> str | None:
    if not chat_id:
        return None
    from app import config as config_module

    if not getattr(config_module, "HOST_CHAT_WORKSPACES", False):
        return None
    root_val = getattr(config_module, "HOST_CHAT_ROOT", "")
    if not root_val:
        return None
    root = Path(root_val)
    ws_dir = root / chat_id
    if not (ws_dir / "meta.json").is_file():
        return None
    try:
        import uuid
        from app.chat_workspace import WorkspaceManager, rebuild_state

        op_id = f"op-{uuid.uuid4().hex[:8]}"
        WorkspaceManager(root).append_op_started(chat_id, op_id, tool, details or {})
        rebuild_state(ws_dir)
        return op_id
    except Exception as exc:
        _journal_error(tool, chat_id, "start", exc)
        return None


def _finish_workspace_journal(
    tool: str,
    chat_id: Optional[str],
    op_id: str | None,
    *,
    ok: bool,
    details: Optional[dict[str, Any]] = None,
) -> None:
    if not chat_id or not op_id:
        return
    from app import config as config_module

    root_val = getattr(config_module, "HOST_CHAT_ROOT", "")
    if not root_val:
        return
    root = Path(root_val)
    ws_dir = root / chat_id
    try:
        from app.chat_workspace import WorkspaceManager, rebuild_state

        WorkspaceManager(root).append_op_result(
            chat_id, op_id, ok, details or {}, kind=tool
        )
        rebuild_state(ws_dir)
    except Exception as exc:
        _journal_error(tool, chat_id, "finish", exc)
