"""Copy-safe error catalog shared by the chat workspace MCP tools.

Codes E1..E6 are stable identifiers; message templates only interpolate
values that were already validated (ids, paths, byte counts), never raw
unvalidated caller input.

The semantic contract for ``ATTRIBUTION_MODE="enforce"`` (E6 BIND_REQUIRED)
is documented once, in the comment block directly above the E6 catalog
entry below; the tool layer gates against it via
``app.chat_identity.is_enforcing()``.
"""

from __future__ import annotations

import errno
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatErrorCode:
    code: str
    name: str
    template: str
    suggestion: str


CHAT_ERROR_CATALOG: dict[str, ChatErrorCode] = {
    "E1": ChatErrorCode(
        "E1",
        "INVALID_CHAT_ID",
        "Invalid chat id: use 6-64 characters from letters, digits, '.', '-' or '_' "
        "and start with a letter or digit.",
        "Pick a chat id of 6-64 characters from letters, digits, '.', '-' or '_', "
        "starting with a letter or digit.",
    ),
    "E2": ChatErrorCode(
        "E2",
        "WORKSPACE_LIMIT",
        "Workspace limit reached: {count} of {limit} workspaces already exist.",
        "Archive or remove an existing workspace before creating a new one.",
    ),
    "E3": ChatErrorCode(
        "E3",
        "QUOTA_EXCEEDED",
        "Chat {chat_id} is over quota: {used_bytes} of {quota_bytes} bytes used.",
        "Remove old files from this workspace or raise its configured quota.",
    ),
    "E4": ChatErrorCode(
        "E4",
        "ROOT_FULL",
        "Workspace root has {free_bytes} free bytes; at least {required_bytes} are required.",
        "Free disk space under HOST_CHAT_ROOT before creating more workspaces.",
    ),
    "E5": ChatErrorCode(
        "E5",
        "SQUAT_DETECTED",
        "Path {path} exists but was not created by botquanganh.",
        "Move or rename the conflicting directory, then bind the workspace again.",
    ),
    # -----------------------------------------------------------------------
    # SEMANTIC CONTRACT -- ATTRIBUTION_MODE="enforce" (E6 BIND_REQUIRED)
    #
    # "enforce" is the hardest attribution level. Every HOST_TOOLS
    # entry-point requires a valid, bound chat identity BEFORE it performs
    # any work:
    #
    # - A chat_id counts as present when it is either supplied as the
    #   tool's ``chat_id`` parameter or already bound to the request
    #   context (app.chat_identity).
    # - The ONLY exempt tool is ``host_workspace_bind`` itself: binding
    #   must stay reachable while unbound, otherwise no session could ever
    #   start.
    # - A present-but-invalid chat id (fails CHAT_ID_PATTERN) is rejected
    #   with E1 INVALID_CHAT_ID in every mode -- never E6.
    # - A missing/unbound chat id under enforce is rejected with E6
    #   BIND_REQUIRED before any side effect: no reads, writes, runs,
    #   notes, journal entries, or audit stamps for the call.
    # - ``{chat_id}`` on E6 carries only an already-validated id (the
    #   bound one or the caller's argument that passed the pattern); it
    #   renders through the copy-safe field guard like every other
    #   template. Raw invalid input never reaches this code because
    #   invalid ids route to E1, whose template interpolates nothing.
    #
    # This catalog defines only the wire contract (code, name, copy,
    # fields). The request gating that emits E6 lives in the tool layer
    # and switches on ``app.chat_identity.is_enforcing()`` alone.
    # -----------------------------------------------------------------------
    "E6": ChatErrorCode(
        "E6",
        "BIND_REQUIRED",
        "Chat binding required: call host_workspace_bind with a valid chat id "
        "(current: {chat_id}) before using any other host tool.",
        "Invoke host_workspace_bind with a valid chat id first, then retry "
        "this tool.",
    ),
    "E7": ChatErrorCode(
        "E7",
        "RESUME_UNAUTHORIZED",
        "Chat '{chat_id}' resume unauthorized: valid resume_token required.",
        "Provide the secret resume_token returned when this workspace was created, or bind a new workspace.",
    ),
}

# Kept identical to app.chat_workspace.CHAT_ID_PATTERN so ids accepted by the
# manager are never rejected here; chat_workspace is optional at import time.
CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")

_INTERNAL_ERROR_PAYLOAD: dict[str, Any] = {
    "ok": False,
    "error": {
        # Not part of the E-catalog: reserved for unmapped failures.
        "code": "INTERNAL",
        "name": "UNMAPPED_ERROR",
        "message": "Internal server error.",
        "suggestion": "Retry later or inspect server logs using an authorized local account.",
    },
}

_NOT_AVAILABLE_SUGGESTION = (
    "This server build does not include the chat workspace infrastructure."
)

# Well-known attribute names on app.chat_workspace exception classes, per code.
# CapacityError/SquatError are the names shipped by app.chat_workspace today.
_DOMAIN_EXCEPTION_NAMES: dict[str, tuple[str, ...]] = {
    "E1": ("InvalidChatIdError", "ChatIdError", "InvalidChatId"),
    "E2": ("CapacityError", "WorkspaceLimitError", "TooManyWorkspacesError"),
    "E3": ("QuotaExceededError", "WorkspaceQuotaExceededError"),
    "E4": ("WorkspaceRootFullError", "RootFullError"),
    "E5": ("SquatError", "SquatDetectedError", "WorkspaceSquatDetectedError"),
    "E6": ("BindRequiredError", "WorkspaceBindRequiredError", "ChatBindRequiredError"),
    "E7": ("ResumeUnauthorizedError", "UnauthorizedResumeError", "InvalidResumeTokenError"),
}

# Fallback when the module cannot be imported: match on class-name fragments.
_NAME_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("invalidchatid", "E1"),
    ("chatidinvalid", "E1"),
    ("workspacelimit", "E2"),
    ("toomanyworkspace", "E2"),
    ("capacityerror", "E2"),
    ("quotaexceeded", "E3"),
    ("quota", "E3"),
    ("rootfull", "E4"),
    ("squat", "E5"),
    # "bind" alone would over-match; require the full "bindrequired" stem so
    # only bind-gating exceptions (BindRequiredError and friends) map to E6.
    ("bindrequired", "E6"),
    ("resumeunauthorized", "E7"),
    ("unauthorizedresume", "E7"),
    ("invalidresumetoken", "E7"),
)


class _MissingFields(dict):
    def __missing__(self, key: str) -> str:
        return "?"


class _SafeField:
    """Render guard for catalog fields: a value whose __format__ or __str__
    raises must degrade to "?" instead of escaping format_map."""

    __slots__ = ("_value",)

    def __init__(self, value: Any) -> None:
        self._value = value

    def __format__(self, spec: str) -> str:
        try:
            return format(self._value, spec)
        except Exception:
            pass
        try:
            return str(self._value)
        except Exception:
            return "?"


class ChatCatalogError(Exception):
    """Domain error carrying a catalog code plus validated format fields."""

    def __init__(self, code: str, **fields: Any) -> None:
        self.code = code
        self.fields = fields
        entry = CHAT_ERROR_CATALOG.get(code)
        super().__init__(entry.name if entry else code)


def validate_chat_id(value: object) -> str:
    if not isinstance(value, str) or not CHAT_ID_PATTERN.fullmatch(value):
        raise ChatCatalogError("E1")
    return value


def chat_error_payload(code: str, **fields: Any) -> dict[str, Any]:
    entry = CHAT_ERROR_CATALOG.get(code)
    if entry is None:
        return dict(_INTERNAL_ERROR_PAYLOAD)
    message = entry.template.format_map(
        _MissingFields({name: _SafeField(value) for name, value in fields.items()})
    )
    return {
        "ok": False,
        "error": {
            "code": entry.code,
            "name": entry.name,
            "message": message,
            "suggestion": entry.suggestion,
        },
    }


def internal_error_payload() -> dict[str, Any]:
    return dict(_INTERNAL_ERROR_PAYLOAD)


def tool_success(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "message": message}
    payload.update(extra)
    return payload


def tool_unavailable(feature: str, reason: str = "") -> dict[str, Any]:
    detail = f"{feature} is not available on this server."
    if reason:
        detail = f"{detail} {reason}"
    return {
        "ok": False,
        "error": {
            "code": "NOT_AVAILABLE",
            "name": "TOOL_UNAVAILABLE",
            "message": detail,
            "suggestion": _NOT_AVAILABLE_SUGGESTION,
        },
    }


def _fields_from_exception(exc: Exception) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for attr in (
        "chat_id",
        "path",
        "count",
        "limit",
        "used_bytes",
        "quota_bytes",
        "free_bytes",
        "required_bytes",
    ):
        value = getattr(exc, attr, None)
        if value is not None:
            fields[attr] = value
    return fields


def _code_from_module_exceptions(exc: Exception, module: object) -> str | None:
    for code, names in _DOMAIN_EXCEPTION_NAMES.items():
        for name in names:
            candidate = getattr(module, name, None)
            if isinstance(candidate, type) and isinstance(exc, candidate):
                return code
    return None


def _code_from_class_name(exc: Exception) -> str | None:
    name = type(exc).__name__.lower()
    for fragment, code in _NAME_FRAGMENTS:
        if fragment in name:
            return code
    return None


def to_tool_error(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, ChatCatalogError):
        return chat_error_payload(exc.code, **exc.fields)
    try:
        import app.chat_workspace as workspace_module
    except Exception:
        # Missing or broken infrastructure must not break error classification.
        workspace_module = None
    if workspace_module is not None:
        code = _code_from_module_exceptions(exc, workspace_module)
        if code:
            return chat_error_payload(code, **_fields_from_exception(exc))
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return chat_error_payload("E4")
    code = _code_from_class_name(exc)
    if code:
        return chat_error_payload(code, **_fields_from_exception(exc))
    return internal_error_payload()
