from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from app.chat_identity import InvalidChatId, validate_chat_id
from app.error_contract import format_error_code
from app.host.executor import execute_host_command
from app.host.files import (
    append_text_file,
    list_directory,
    make_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)
from app.host.policy import inspect_host_command
from app.logging_audit import (
    effective_attribution_mode,
    log_audit_event,
    stamp_chat_id,
)
from app.mcp_server import mcp
from app.security import format_error_response

_STATE_CHANGING_TOOLS = frozenset(
    {
        "host_write_file",
        "host_replace_in_file",
        "host_append_file",
        "host_make_directory",
        "host_run_command",
    }
)


def _invalid_chat_id_payload() -> dict[str, Any]:
    # chat_errors is optional infrastructure: fall back to a hand-built E1
    # payload with the same envelope if the module ever moves or changes.
    try:
        from app.chat_errors import ChatCatalogError, to_tool_error

        return to_tool_error(ChatCatalogError("E1"))
    except ImportError:
        return {
            "ok": False,
            "error": {
                "code": "E1",
                "name": "INVALID_CHAT_ID",
                "message": (
                    "Invalid chat id: use 6-64 characters from letters, digits, "
                    "'.', '-' or '_' and start with a letter or digit."
                ),
                "suggestion": (
                    "Pick a chat id of 6-64 characters from letters, digits, '.', "
                    "'-' or '_', starting with a letter or digit."
                ),
            },
        }


# Tools exempt from enforce-mode binding: host_workspace_bind IS the way in,
# so demanding a prior bind from it would deadlock every caller.
BIND_EXEMPT_TOOLS = frozenset({"host_workspace_bind", "host_workspace_list"})



def _is_enforcing_mode() -> bool:
    """True only when ATTRIBUTION_MODE=enforce is actually active.

    Prefers ``chat_identity.is_enforcing()`` from the concurrent contract
    change; until that helper lands (or if it ever disappears) a defensive raw
    read of the config value keeps the decision working locally.  Missing or
    unknown values behave as today: not enforcing.
    """
    try:
        from app.chat_identity import is_enforcing

        return bool(is_enforcing())
    except ImportError:
        pass
    from app import config as config_module

    raw = str(getattr(config_module, "ATTRIBUTION_MODE", "") or "").strip().lower()
    return raw == "enforce"


def _context_chat_id() -> Optional[str]:
    """Defensive lookup of a context-bound chat id, if that layer exists."""
    try:
        from app.chat_identity import get_chat_id

        candidate = get_chat_id()
    except ImportError:
        return None
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _bind_required_payload(tool: str) -> dict[str, Any]:
    """Structured E6 payload telling the caller to bind a chat id first.

    Uses the shared catalog once the concurrent E6 entry exists; otherwise a
    hand-built payload with the same envelope shape.  Either way the reply
    names host_workspace_bind as the way in.
    """
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
                    f"{tool} requires a bound chat id while "
                    "ATTRIBUTION_MODE=enforce."
                ),
                "suggestion": (
                    "Call host_workspace_bind with a valid chat id first, then "
                    "pass that chat_id to every host tool call."
                ),
            },
        }
    error = payload.get("error")
    if isinstance(error, dict):
        combined = f"{error.get('message', '')} {error.get('suggestion', '')}"
        if "host_workspace_bind" not in combined:
            error["message"] = (
                f"{str(error.get('message', '')).strip()} "
                "Call host_workspace_bind first."
            ).strip()
    return payload


def _guard_chat_id(
    tool: str, chat_id: Optional[str]
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Validate an optional caller chat id and enforce strict/enforce modes.

    Returns (validated_id, None) when the call may proceed, or (None, payload)
    with a structured error when it must be rejected.

    - enforce: every call needs a valid chat id, reads included. A missing id
      falls back to a context-bound one; with neither, the call is rejected
      with E6 before any executor or filesystem function runs. An invalid id
      is still E1. host_workspace_bind is exempt (see BIND_EXEMPT_TOOLS).
    - strict: only state-changing tools need an id (unchanged).
    - off/tag: validate whatever id is supplied, nothing more (unchanged).
    """
    resolved = chat_id
    if resolved is None and _is_enforcing_mode():
        resolved = _context_chat_id()
        if resolved is None:
            try:
                from app.chat_identity import get_active_workspace
                resolved = get_active_workspace()
            except Exception:
                pass
        if resolved is None:
            return None, _bind_required_payload(tool)

    if resolved is None:
        if tool in _STATE_CHANGING_TOOLS and effective_attribution_mode() == "strict":
            return None, format_error_code(
                "INVALID_ARGUMENT",
                message=(
                    f"{tool} requires chat_id while ATTRIBUTION_MODE=strict: "
                    "state-changing operations must carry an attributable chat id."
                ),
            )
        return None, None
    try:
        validated = validate_chat_id(resolved)
    except InvalidChatId:
        return None, _invalid_chat_id_payload()

    if _is_enforcing_mode() and tool not in BIND_EXEMPT_TOOLS:
        from app import config as config_module

        if getattr(config_module, "HOST_CHAT_WORKSPACES", False):
            root = Path(getattr(config_module, "HOST_CHAT_ROOT", ""))
            if root and not (root / validated / "meta.json").is_file():
                return None, _bind_required_payload(tool)

    return validated, None


def _stamp_chat_id(
    details: dict[str, Any], chat_id: Optional[str]
) -> dict[str, Any]:
    """Stamp like logging_audit.stamp_chat_id, extended for enforce mode.

    logging_audit only knows off/tag/strict, so an enforce deployment reads as
    "off" there and would silently drop the attribution stamp. Enforce exists
    precisely so every executed action is attributable, so the stamp is applied
    directly whenever the mode helper reports enforcing.
    """
    if chat_id and _is_enforcing_mode():
        details["chat_id"] = chat_id
        return details
    return stamp_chat_id(details, chat_id)


def _record_tool_call(
    tool: str,
    chat_id: Optional[str],
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Emit one attribution-bearing audit event only when there is something.

    With no chat id stamped and no extra detail, today's audit stream stays
    byte-identical; stamping itself respects ATTRIBUTION_MODE.
    """
    payload = {
        key: value for key, value in (details or {}).items() if value is not None
    }
    _stamp_chat_id(payload, chat_id)
    if payload:
        log_audit_event("HOST_TOOL_CALL", {"tool": tool, **payload})


def _journal_error(tool: str, chat_id: str, phase: str, exc: Exception) -> None:
    """Surface best-effort journal failures without leaking exception details."""
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
    """Write the durable op_started record before the host operation begins."""
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
        # STATE.md is a cache, but refreshing it before execution makes crash
        # recovery immediately show the operation as pending.
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
    """Pair a prior op_started record with its durable completion result."""
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
        _journal_error(tool, chat_id, "result", exc)


def _record_workspace_journal(
    tool: str,
    chat_id: Optional[str],
    details: Optional[dict[str, Any]] = None,
    ok: bool = True,
) -> None:
    """Compatibility helper for call sites that cannot yet bracket execution."""
    op_id = _begin_workspace_journal(tool, chat_id, details)
    _finish_workspace_journal(tool, chat_id, op_id, ok=ok, details=details)


def _normalize_intent(intent: Optional[str]) -> Optional[str]:
    """Collapse an intent to a single stripped line capped at 200 characters."""
    if intent is None:
        return None
    cleaned = " ".join(str(intent).split())
    return cleaned[:200] or None


@mcp.tool(
    name="host_list_directory",
    description=(
        "List files and directories on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads)."
    ),
)
def host_list_directory(
    path: str = ".",
    max_entries: int = 500,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_list_directory", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {"path": path, "max_entries": max_entries}
    journal_op = _begin_workspace_journal(
        "host_list_directory", validated, journal_details
    )
    try:
        result = list_directory(path, max_entries=max_entries)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_list_directory", validated)
    _finish_workspace_journal(
        "host_list_directory",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_read_file",
    description=(
        "Read a UTF-8 text file from the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). Absolute paths "
        "within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_bytes: Optional[int] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_read_file", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "max_bytes": max_bytes,
    }
    journal_op = _begin_workspace_journal("host_read_file", validated, journal_details)
    try:
        result = read_text_file(
            path,
            start_line=start_line,
            end_line=end_line,
            max_bytes=max_bytes,
        )
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_read_file", validated)
    _finish_workspace_journal(
        "host_read_file",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_write_file",
    description=(
        "Create or overwrite a UTF-8 text file on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads) to keep the host tidy. "
        "Absolute paths within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_write_file(
    path: str,
    content: str,
    overwrite: bool = True,
    create_parents: bool = True,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_write_file", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {
        "path": path,
        "size_bytes": len(content.encode("utf-8")),
        "overwrite": overwrite,
        "create_parents": create_parents,
    }
    journal_op = _begin_workspace_journal("host_write_file", validated, journal_details)
    try:
        result = write_text_file(
            path,
            content,
            overwrite=overwrite,
            create_parents=create_parents,
        )
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_write_file", validated)
    _finish_workspace_journal(
        "host_write_file",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_replace_in_file",
    description=(
        "Replace text in a host file and require the expected number of matches "
        "before writing."
    ),
)
def host_replace_in_file(
    path: str,
    old: str,
    new: str,
    expected_count: int = 1,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_replace_in_file", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {"path": path, "expected_count": expected_count}
    journal_op = _begin_workspace_journal(
        "host_replace_in_file", validated, journal_details
    )
    try:
        result = replace_text_in_file(
            path,
            old,
            new,
            expected_count=expected_count,
        )
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_replace_in_file", validated)
    _finish_workspace_journal(
        "host_replace_in_file",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_append_file",
    description="Append UTF-8 text to a file on the host machine.",
)
def host_append_file(
    path: str,
    content: str,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_append_file", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {"path": path, "size_bytes": len(content.encode("utf-8"))}
    journal_op = _begin_workspace_journal("host_append_file", validated, journal_details)
    try:
        result = append_text_file(path, content)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_append_file", validated)
    _finish_workspace_journal(
        "host_append_file",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_make_directory",
    description=(
        "Create a directory on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). Absolute paths "
        "within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_make_directory(
    path: str,
    parents: bool = True,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_make_directory", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {"path": path, "parents": parents}
    journal_op = _begin_workspace_journal(
        "host_make_directory", validated, journal_details
    )
    try:
        result = make_directory(path, parents=parents)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_make_directory", validated)
    _finish_workspace_journal(
        "host_make_directory",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_search_text",
    description=(
        "Search text recursively across host files while excluding common build, "
        "VCS, virtual-environment, and dependency directories."
    ),
)
def host_search_text(
    query: str,
    path: str = ".",
    case_sensitive: bool = False,
    max_results: int = 100,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_search_text", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {
        "query": query,
        "path": path,
        "case_sensitive": case_sensitive,
        "max_results": max_results,
    }
    journal_op = _begin_workspace_journal("host_search_text", validated, journal_details)
    try:
        result = search_text(
            query,
            path=path,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_search_text", validated)
    _finish_workspace_journal(
        "host_search_text",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_check_command",
    description=(
        "Inspect a shell command against the server-side host policy without "
        "executing it. There is no caller-supplied approval bypass."
    ),
)
def host_check_command(
    command: str,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_check_command", chat_id)
    if rejection is not None:
        return rejection
    journal_details = {"command": command}
    journal_op = _begin_workspace_journal(
        "host_check_command", validated, journal_details
    )
    try:
        result = {"ok": True, **inspect_host_command(command)}
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_check_command", validated)
    _finish_workspace_journal(
        "host_check_command",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_details,
    )
    return result


@mcp.tool(
    name="host_run_command",
    description=(
        "Execute a shell command directly on the user's host machine via bash. "
        "Default timeout is 60 seconds (1 minute). Maximum allowed timeout is 300 seconds (5 minutes). "
        "Pass timeout_seconds to adjust (up to 300s) or 0 to run without timeout until completion. "
        "Relative cwd values are resolved from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). "
        "The default working directory is HOST_DEFAULT_DIR. Destructive commands are blocked."
    ),
)
def host_run_command(
    command: str,
    timeout_seconds: Optional[int] = None,
    cwd: Optional[str] = None,
    intent: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:

    validated, rejection = _guard_chat_id("host_run_command", chat_id)
    if rejection is not None:
        return rejection
    cleaned_intent = _normalize_intent(intent)
    journal_start = {
        "command": command,
        "intent": cleaned_intent,
        "cwd": cwd,
        "timeout_seconds": timeout_seconds,
    }
    journal_op = _begin_workspace_journal(
        "host_run_command", validated, journal_start
    )
    try:
        execute_kwargs: dict[str, Any] = {
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
            "activity_source": "mcp",
            "activity_chat_id": validated,
        }
        if journal_op:
            execute_kwargs["activity_operation_id"] = journal_op
        result = execute_host_command(command, **execute_kwargs)
    except Exception as exc:
        result = format_error_response(exc)
    attributed: dict[str, Any] = {}
    _stamp_chat_id(attributed, validated)
    if cleaned_intent is not None:
        attributed["intent"] = cleaned_intent
    if attributed:
        # Hash instead of raw command to match the executor's audit posture.
        attributed.setdefault(
            "command_sha256", hashlib.sha256(command.encode("utf-8")).hexdigest()
        )
        log_audit_event("HOST_TOOL_CALL", {"tool": "host_run_command", **attributed})
    journal_result = {
        "exit_code": result.get("exit_code") if isinstance(result, dict) else None,
        "stdout_truncated": result.get("stdout_truncated") if isinstance(result, dict) else None,
        "stderr_truncated": result.get("stderr_truncated") if isinstance(result, dict) else None,
        "output_incomplete": result.get("output_incomplete") if isinstance(result, dict) else None,
    }
    _finish_workspace_journal(
        "host_run_command",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=journal_result,
    )
    return result
