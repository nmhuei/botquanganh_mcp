from __future__ import annotations

import hashlib
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


def _guard_chat_id(
    tool: str, chat_id: Optional[str]
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Validate an optional caller chat id and enforce strict-mode writes.

    Returns (validated_id, None) when the call may proceed, or (None, payload)
    with a structured error when it must be rejected.
    """
    if chat_id is None:
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
        return validate_chat_id(chat_id), None
    except InvalidChatId:
        return None, _invalid_chat_id_payload()


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
    stamp_chat_id(payload, chat_id)
    if payload:
        log_audit_event("HOST_TOOL_CALL", {"tool": tool, **payload})


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
    try:
        result = list_directory(path, max_entries=max_entries)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_list_directory", validated)
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
    try:
        result = append_text_file(path, content)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_append_file", validated)
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
    try:
        result = make_directory(path, parents=parents)
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_make_directory", validated)
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
    try:
        result = {"ok": True, **inspect_host_command(command)}
    except Exception as exc:
        result = format_error_response(exc)
    _record_tool_call("host_check_command", validated)
    return result


@mcp.tool(
    name="host_run_command",
    description=(
        "Execute a shell command directly on the user's host machine. Relative cwd "
        "values are resolved from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). "
        "The default working directory is HOST_DEFAULT_DIR. Destructive commands are blocked."
    ),
)
def host_run_command(
    command: str,
    timeout_seconds: int = 30,
    cwd: Optional[str] = None,
    intent: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    validated, rejection = _guard_chat_id("host_run_command", chat_id)
    if rejection is not None:
        return rejection
    cleaned_intent = _normalize_intent(intent)
    try:
        result = execute_host_command(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            activity_source="mcp",
        )
    except Exception as exc:
        result = format_error_response(exc)
    attributed: dict[str, Any] = {}
    stamp_chat_id(attributed, validated)
    if cleaned_intent is not None:
        attributed["intent"] = cleaned_intent
    if attributed:
        # Hash instead of raw command to match the executor's audit posture.
        attributed.setdefault(
            "command_sha256", hashlib.sha256(command.encode("utf-8")).hexdigest()
        )
        log_audit_event("HOST_TOOL_CALL", {"tool": "host_run_command", **attributed})
    return result
