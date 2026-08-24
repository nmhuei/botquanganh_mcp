"""Request-scoped correlation data for HTTP and FastMCP observability.

Only opaque identifiers and routing metadata live here.  Tool arguments,
authorization values, and response bodies must never be stored in this module.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token


_REQUEST_ID = ContextVar("mcp_request_id", default="")
_REQUEST_PATH = ContextVar("mcp_request_path", default="")
_CLIENT_HOST = ContextVar("mcp_client_host", default="")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def new_request_id(candidate: str | None = None) -> str:
    """Return a safe correlation id, preserving a valid caller-supplied value."""
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return f"bqa-{uuid.uuid4()}"


def set_request_context(
    request_id: str,
    *,
    path: str = "",
    client_host: str = "",
) -> tuple[Token[str], Token[str], Token[str]]:
    return (
        _REQUEST_ID.set(request_id),
        _REQUEST_PATH.set(path),
        _CLIENT_HOST.set(client_host),
    )


def reset_request_context(tokens: tuple[Token[str], Token[str], Token[str]]) -> None:
    request_id, path, client_host = tokens
    _REQUEST_ID.reset(request_id)
    _REQUEST_PATH.reset(path)
    _CLIENT_HOST.reset(client_host)


def request_id() -> str:
    return _REQUEST_ID.get()


def request_path() -> str:
    return _REQUEST_PATH.get()


def client_host() -> str:
    return _CLIENT_HOST.get()
