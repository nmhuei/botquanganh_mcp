from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import app.config


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    http_status: int
    suggestion: str


class ServiceBusyError(RuntimeError):
    """Raised when bounded service capacity cannot accept more work."""


ERROR_SPECS: dict[str, ErrorSpec] = {
    "INVALID_ARGUMENT": ErrorSpec(
        "INVALID_ARGUMENT", 400, "Check the request arguments and configured limits."
    ),
    "AUTH_REQUIRED": ErrorSpec(
        "AUTH_REQUIRED", 401, "Provide a valid gateway token."
    ),
    "POLICY_BLOCKED": ErrorSpec(
        "POLICY_BLOCKED", 403, "Check HOST_WORKSPACE_DIR and HOST_COMMAND_POLICY."
    ),
    "FILE_NOT_FOUND": ErrorSpec(
        "FILE_NOT_FOUND", 404, "Check the requested path relative to HOST_WORKSPACE_DIR."
    ),
    "TIMEOUT": ErrorSpec(
        "TIMEOUT", 408, "Use a shorter operation or increase the configured timeout limit."
    ),
    "FILE_EXISTS": ErrorSpec(
        "FILE_EXISTS", 409, "Choose a different path or allow overwrite explicitly."
    ),
    "RATE_LIMITED": ErrorSpec(
        "RATE_LIMITED", 429, "Retry after the interval reported by the server."
    ),
    "SERVICE_BUSY": ErrorSpec(
        "SERVICE_BUSY", 503, "Retry when command execution capacity becomes available."
    ),
    "INTERNAL_ERROR": ErrorSpec(
        "INTERNAL_ERROR", 500, "Check server and audit logs using an authorized local account."
    ),
}


def classify_exception(exc: Exception) -> ErrorSpec:
    if isinstance(exc, ServiceBusyError):
        return ERROR_SPECS["SERVICE_BUSY"]
    if isinstance(exc, PermissionError):
        return ERROR_SPECS["POLICY_BLOCKED"]
    if isinstance(exc, FileExistsError):
        return ERROR_SPECS["FILE_EXISTS"]
    if isinstance(exc, FileNotFoundError):
        return ERROR_SPECS["FILE_NOT_FOUND"]
    if isinstance(exc, TimeoutError):
        return ERROR_SPECS["TIMEOUT"]
    if isinstance(exc, (TypeError, ValueError, NotADirectoryError, IsADirectoryError)):
        return ERROR_SPECS["INVALID_ARGUMENT"]
    return ERROR_SPECS["INTERNAL_ERROR"]


def _redact_known_paths(message: str) -> str:
    replacements: list[tuple[str, str]] = []
    for path, label in (
        (app.config.HOST_WORKSPACE_DIR, "<workspace>"),
        (app.config.BASE_DIR, "<repo>"),
        (Path.home(), "~"),
    ):
        try:
            raw = str(path.resolve())
        except OSError:
            raw = str(path)
        if raw:
            replacements.append((raw, label))
    for raw, label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        message = message.replace(raw, label)
    return message


def public_exception_message(exc: Exception, spec: ErrorSpec) -> str:
    if spec.code == "INTERNAL_ERROR":
        return "Internal server error."
    message = str(exc).strip() or spec.code.replace("_", " ").title()
    return _redact_known_paths(message)


def format_error_code(
    code: str,
    *,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = ERROR_SPECS.get(code, ERROR_SPECS["INTERNAL_ERROR"])
    detail: dict[str, Any] = {
        "code": spec.code,
        "message": message or spec.code.replace("_", " ").title(),
        "suggestion": spec.suggestion,
    }
    if extra:
        detail.update(extra)
    return {"ok": False, "error": detail}


def format_exception_error(exc: Exception) -> dict[str, Any]:
    spec = classify_exception(exc)
    return format_error_code(
        spec.code,
        message=public_exception_message(exc, spec),
    )


def http_status_for_error_code(code: str) -> int:
    return ERROR_SPECS.get(code, ERROR_SPECS["INTERNAL_ERROR"]).http_status


def http_status_for_exception(exc: Exception) -> int:
    return classify_exception(exc).http_status


def http_status_for_result(result: Any) -> int:
    if not isinstance(result, dict) or result.get("ok", True):
        return 200
    # A command exchange completed successfully at the service layer even when
    # the child process itself exits non-zero.
    if "exit_code" in result and not result.get("error"):
        return 200
    error = result.get("error")
    code = str(error.get("code", "")) if isinstance(error, dict) else ""
    return http_status_for_error_code(code)


def openapi_error_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["ok", "error"],
        "properties": {
            "ok": {"type": "boolean", "const": False},
            "error": {
                "type": "object",
                "required": ["code", "message", "suggestion"],
                "properties": {
                    "code": {"type": "string", "enum": sorted(ERROR_SPECS)},
                    "message": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": False,
    }
