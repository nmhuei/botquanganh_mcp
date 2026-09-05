"""Scope-constrained HTTP requests for one active, authorized CTF case.

This service is deliberately MCP-free.  The caller supplies an already-bound
workspace manager, and tests can inject both the HTTP client and DNS resolver.
Every request (including a redirect hop) re-loads the active case and validates
the exact destination immediately before handing the request to ``httpx``.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
import socket
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.chat_workspace import WorkspaceManager
from app.ctf.case_scope import (
    CaseRecord,
    _canonical_host,
    _netloc,
    _parsed_origin,
    canonicalize_origin,
    load_active_case,
)


SUPPORTED_METHODS = frozenset({"GET", "HEAD", "POST"})
FORBIDDEN_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "connection", "transfer-encoding"}
)
MAX_REQUEST_HEADERS = 32
MAX_HEADER_NAME_BYTES = 128
MAX_HEADER_VALUE_BYTES = 4_096
MAX_REQUEST_HEADER_BYTES = 16_384
MAX_REQUEST_BODY_BYTES = 65_536
MAX_RESPONSE_BYTES = 200_000
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 3

_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_CROSS_ORIGIN_SECRET_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)
_ENTITY_HEADERS = frozenset(
    {"content-encoding", "content-language", "content-location", "content-type"}
)
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_MAX_REDIRECT_LOCATION_BYTES = 4_096
_MAX_CONTENT_TYPE_BYTES = 1_024
_Resolve = Callable[..., list[tuple[Any, ...]]]
_HeaderItems = tuple[tuple[str, str], ...]


def _normalize_method(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("method must be GET, HEAD, or POST.")
    method = value.upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError("method must be GET, HEAD, or POST.")
    return method


def _validate_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("path must be text.")
    path = value or "/"
    if any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in path):
        raise ValueError("path must not contain whitespace or control characters.")
    if "\\" in path:
        raise ValueError("path must not contain backslashes.")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or path.startswith("//"):
        raise ValueError("path must not contain an absolute or network-path URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("path must not contain credentials.")
    if parsed.fragment:
        raise ValueError("path must not contain a fragment.")
    if path.startswith("?"):
        return f"/{path}"
    if not path.startswith("/"):
        raise ValueError("path must begin with '/' or '?'.")
    return path


def _encode_ascii_header_part(value: str, *, what: str, maximum: int) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{what} must contain ASCII characters only.") from exc
    if len(encoded) > maximum:
        raise ValueError(f"{what} exceeds its byte limit.")
    return encoded


def _validate_headers(headers: Mapping[str, str] | None) -> _HeaderItems:
    if headers is None:
        return ()
    if not isinstance(headers, Mapping):
        raise ValueError("headers must be a mapping of names to text values.")
    try:
        items = list(headers.items())
    except (AttributeError, TypeError) as exc:
        raise ValueError("headers must be a mapping of names to text values.") from exc
    if len(items) > MAX_REQUEST_HEADERS:
        raise ValueError(f"headers must contain at most {MAX_REQUEST_HEADERS} entries.")

    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    total_bytes = 0
    for name, value in items:
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("header names and values must be text.")
        if not name or _HEADER_NAME.fullmatch(name) is None:
            raise ValueError("header name is invalid.")
        lowered = name.lower()
        if lowered in FORBIDDEN_REQUEST_HEADERS:
            raise ValueError(f"header is caller-controlled and forbidden: {name}.")
        if lowered in seen:
            raise ValueError("header names must be unique ignoring case.")
        seen.add(lowered)

        name_bytes = _encode_ascii_header_part(
            name, what="header name", maximum=MAX_HEADER_NAME_BYTES
        )
        value_bytes = _encode_ascii_header_part(
            value, what="header value", maximum=MAX_HEADER_VALUE_BYTES
        )
        if any(byte < 0x20 and byte != 0x09 for byte in value_bytes) or 0x7F in value_bytes:
            raise ValueError("header value contains a prohibited control character.")
        total_bytes += len(name_bytes) + len(value_bytes) + 4
        if total_bytes > MAX_REQUEST_HEADER_BYTES:
            raise ValueError("request headers exceed the total byte limit.")
        normalized.append((name, value))
    return tuple(normalized)


def _validate_body(method: str, body: str | None) -> bytes | None:
    if body is None:
        return None
    if method != "POST":
        raise ValueError("body is supported only for POST requests.")
    if not isinstance(body, str):
        raise ValueError("body must be UTF-8 text.")
    try:
        encoded = body.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("body must be valid UTF-8 text.") from exc
    if len(encoded) > MAX_REQUEST_BODY_BYTES:
        raise ValueError(
            f"body must be at most {MAX_REQUEST_BODY_BYTES:,} UTF-8 bytes."
        )
    return encoded


def _initial_url(origin: str, path: str, record: CaseRecord) -> str:
    if not isinstance(origin, str) or origin not in record.authorized_origins:
        raise ValueError("origin must be an exact authorized origin from the active case.")
    return str(httpx.URL(f"{origin}{_validate_path(path)}"))


def _authorized_origin_candidate(value: str, record: CaseRecord) -> str:
    """Normalize an origin enough to check case authority without DNS.

    Redirect destinations are untrusted.  For public cases, full
    ``canonicalize_origin`` resolves hostnames to enforce their public-address
    boundary, but that lookup must only happen after the destination is known
    to be an exact origin already granted by the active case.
    """
    parsed, port = _parsed_origin(value)
    scheme = parsed.scheme.lower()
    host, address = _canonical_host(parsed.hostname)

    if record.network_mode == "public_https":
        if scheme != "https":
            raise ValueError("public_https cases accept HTTPS origins only.")
        effective_port = 443 if port is None else port
        if not 1 <= effective_port <= 65535:
            raise ValueError("public_https origin port must be between 1 and 65535.")
        return f"https://{_netloc(host, address, None if effective_port == 443 else effective_port)}"

    if scheme not in {"http", "https"}:
        raise ValueError("local_instance cases accept HTTP or HTTPS origins only.")
    if port is None or not 1 <= port <= 65535:
        raise ValueError("local_instance origins require an explicit port.")
    if host == "localhost":
        return f"{scheme}://localhost:{port}"
    if address is None or not address.is_loopback:
        raise ValueError("local_instance origins must use literal loopback or localhost.")
    return f"{scheme}://{_netloc(host, address, port)}"


def _bounded_header_value(value: str, *, name: str, maximum: int) -> str:
    encoded = value.encode("latin-1", errors="replace")
    if len(encoded) > maximum:
        raise ValueError(f"response {name} exceeds its byte limit.")
    return value


def _validated_scoped_url(
    value: str,
    record: CaseRecord,
    resolver: _Resolve,
    *,
    redirect: bool,
) -> tuple[str, str]:
    noun = "redirect target" if redirect else "target URL"
    if not isinstance(value, str) or not value:
        raise ValueError(f"{noun} must be a non-empty URL.")
    if "\\" in value or any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    ):
        raise ValueError(f"{noun} contains prohibited characters.")
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{noun} must be absolute.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{noun} must not contain credentials.")
    if parsed.fragment:
        raise ValueError(f"{noun} must not contain a fragment.")

    raw_origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    candidate_origin = _authorized_origin_candidate(raw_origin, record)
    if candidate_origin not in record.authorized_origins:
        raise ValueError(f"{noun} must use an exact authorized origin.")
    canonical_origin = canonicalize_origin(
        raw_origin, record.network_mode, resolver=resolver
    )
    if canonical_origin not in record.authorized_origins:
        raise ValueError(f"{noun} must use an exact authorized origin.")

    path_and_query = parsed.path or "/"
    if parsed.query:
        path_and_query = f"{path_and_query}?{parsed.query}"
    return str(httpx.URL(f"{canonical_origin}{path_and_query}")), canonical_origin


def _bounded_response_body(response: httpx.Response) -> tuple[str, int, bool]:
    content = bytearray()
    truncated = False
    for chunk in response.iter_bytes(chunk_size=8_192):
        if not chunk:
            continue
        remaining = MAX_RESPONSE_BYTES - len(content)
        if remaining <= 0:
            truncated = True
            break
        content.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
            break
    raw = bytes(content)
    return raw.decode("utf-8", errors="replace"), len(raw), truncated


def _without_headers(headers: _HeaderItems, blocked: frozenset[str]) -> _HeaderItems:
    return tuple((name, value) for name, value in headers if name.lower() not in blocked)


def _redirect_method(status_code: int, method: str) -> str:
    if status_code == 303 and method != "HEAD":
        return "GET"
    if status_code in {301, 302} and method == "POST":
        return "GET"
    return method


def _request_extensions() -> dict[str, dict[str, float]]:
    timeout = float(REQUEST_TIMEOUT_SECONDS)
    return {
        "timeout": {
            "connect": timeout,
            "read": timeout,
            "write": timeout,
            "pool": timeout,
        }
    }


def request_target(
    manager: WorkspaceManager,
    chat_id: str,
    *,
    case_id: str,
    origin: str,
    path: str = "/",
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: str | None = None,
    follow_redirects: bool = False,
    client: httpx.Client | None = None,
    resolver: _Resolve = socket.getaddrinfo,
) -> dict[str, Any]:
    """Send one bounded request, plus only explicitly enabled safe redirects.

    ``origin`` must exactly match a canonical origin stored in the active case;
    callers can vary only ``path`` and its query string.  A supplied client is
    used only as the external HTTP boundary: its headers, cookies, auth,
    redirect policy, and timeout defaults are not inherited.
    """
    request_method = _normalize_method(method)
    if not isinstance(follow_redirects, bool):
        raise ValueError("follow_redirects must be a boolean.")
    request_headers = _validate_headers(headers)
    request_body = _validate_body(request_method, body)

    record = load_active_case(
        manager, chat_id, case_id=case_id, resolver=resolver
    )
    current_url = _initial_url(origin, path, record)
    current_origin = origin
    redirects: list[dict[str, Any]] = []
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )

    try:
        while True:
            # Re-loading by case id closes the replacement race between hops.
            record = load_active_case(
                manager, chat_id, case_id=case_id, resolver=resolver
            )
            current_url, checked_origin = _validated_scoped_url(
                current_url, record, resolver, redirect=bool(redirects)
            )
            current_origin = checked_origin
            request = httpx.Request(
                request_method,
                current_url,
                headers=request_headers,
                content=request_body,
                extensions=_request_extensions(),
            )
            try:
                response = http_client.send(
                    request,
                    stream=True,
                    auth=None,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise RuntimeError(f"HTTP {request_method} failed: {exc}") from exc

            try:
                location = response.headers.get("location")
                if (
                    follow_redirects
                    and response.status_code in _REDIRECT_STATUS_CODES
                    and location
                ):
                    if len(redirects) >= MAX_REDIRECTS:
                        raise ValueError("Redirect limit exceeded.")
                    location = _bounded_header_value(
                        location,
                        name="redirect location",
                        maximum=_MAX_REDIRECT_LOCATION_BYTES,
                    )
                    joined = urljoin(str(response.url), location)
                    next_url, next_origin = _validated_scoped_url(
                        joined, record, resolver, redirect=True
                    )
                    redirects.append(
                        {
                            "status_code": response.status_code,
                            "from": str(response.url),
                            "to": next_url,
                        }
                    )
                    next_method = _redirect_method(response.status_code, request_method)
                    if next_method != request_method:
                        request_headers = _without_headers(request_headers, _ENTITY_HEADERS)
                        request_body = None
                    if next_origin != current_origin:
                        request_headers = _without_headers(
                            request_headers, _CROSS_ORIGIN_SECRET_HEADERS
                        )
                    request_method = next_method
                    current_url = next_url
                    current_origin = next_origin
                    continue

                content_type = _bounded_header_value(
                    response.headers.get("content-type", ""),
                    name="content type",
                    maximum=_MAX_CONTENT_TYPE_BYTES,
                )
                response_body, body_bytes, truncated = _bounded_response_body(response)
                return {
                    "ok": True,
                    "method": request_method,
                    "url": str(response.url),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "body": response_body,
                    "body_bytes": body_bytes,
                    "body_truncated": truncated,
                    "redirects": redirects,
                }
            finally:
                response.close()
    finally:
        if owns_client:
            http_client.close()
