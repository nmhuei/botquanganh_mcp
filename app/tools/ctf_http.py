"""Bounded, read-only HTTP fetches for explicitly authorized CTF URLs."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from fastmcp.apps import AppConfig

from app.mcp_server import mcp
from app.security import format_error_response
from app.ui.ctf_fetch_result import CTF_FETCH_RESULT_WIDGET_URI

_DEFAULT_TIMEOUT_SECONDS = 10
_MAX_TIMEOUT_SECONDS = 15
_DEFAULT_MAX_BYTES = 65_536
_MIN_MAX_BYTES = 1_024
_MAX_MAX_BYTES = 200_000
_MAX_REDIRECTS = 3
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_USER_AGENT = "BotQuangAnh-CTF-Fetch/1.0"


def _is_public_address(value: str) -> bool:
    return ipaddress.ip_address(value).is_global


def _validate_public_https_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("url must be a non-empty HTTPS URL.")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError("url must not contain whitespace.")

    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Only absolute HTTPS URLs are supported.")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not supported.")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("url contains an invalid port.") from exc

    hostname = parsed.hostname
    try:
        addresses = {str(ipaddress.ip_address(hostname))}
    except ValueError:
        try:
            results = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Unable to resolve URL host: {hostname}.") from exc
        addresses = {result[4][0] for result in results if result[4]}

    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ValueError("URL host must resolve only to public IP addresses.")

    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


def _bounded_body(response: httpx.Response, max_bytes: int) -> tuple[str, bool]:
    content = bytearray()
    truncated = False
    for chunk in response.iter_bytes():
        remaining = max_bytes - len(content)
        if remaining <= 0:
            truncated = True
            break
        content.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
            break
    return bytes(content).decode("utf-8", errors="replace"), truncated


def fetch_ctf_url(
    url: str,
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    follow_redirects: bool = True,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch one public HTTPS URL with GET only; never scan or enumerate."""
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be an integer between 1 and {_MAX_TIMEOUT_SECONDS}."
        )
    if not isinstance(max_bytes, int) or not _MIN_MAX_BYTES <= max_bytes <= _MAX_MAX_BYTES:
        raise ValueError(
            f"max_bytes must be an integer between {_MIN_MAX_BYTES} and {_MAX_MAX_BYTES}."
        )
    if not isinstance(follow_redirects, bool):
        raise ValueError("follow_redirects must be a boolean.")

    current_url = _validate_public_https_url(url)
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": _USER_AGENT},
    )
    redirects: list[dict[str, Any]] = []

    try:
        for _ in range(_MAX_REDIRECTS + 1):
            with http_client.stream("GET", current_url) as response:
                location = response.headers.get("location")
                if (
                    follow_redirects
                    and response.status_code in _REDIRECT_STATUS_CODES
                    and location
                ):
                    if len(redirects) >= _MAX_REDIRECTS:
                        raise ValueError("Redirect limit exceeded.")
                    next_url = _validate_public_https_url(urljoin(str(response.url), location))
                    redirects.append(
                        {
                            "status_code": response.status_code,
                            "from": str(response.url),
                            "to": next_url,
                        }
                    )
                    current_url = next_url
                    continue

                body, truncated = _bounded_body(response, max_bytes)
                return {
                    "ok": True,
                    "method": "GET",
                    "url": current_url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "body": body,
                    "body_truncated": truncated,
                    "redirects": redirects,
                }
    except httpx.HTTPError as exc:
        raise RuntimeError(f"HTTP GET failed: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()

    raise RuntimeError("HTTP GET did not produce a response.")  # pragma: no cover


@mcp.tool(
    name="ctf_fetch_url",
    description=(
        "Fetch exactly one explicitly authorized public HTTPS CTF URL with a read-only "
        "HTTP GET. Use this for a basic page fetch only; it never fuzzes, crawls, "
        "enumerates endpoints, or sends write requests."
    ),
    annotations={
        "title": "Fetch authorized CTF URL",
        "readOnlyHint": True,
        "openWorldHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_fetch_url(
    url: str,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    follow_redirects: bool = True,
) -> dict[str, Any]:
    """Run a single bounded read-only GET for an authorized CTF challenge URL."""
    try:
        return fetch_ctf_url(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            follow_redirects=follow_redirects,
        )
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="ctf_render_fetch_result",
    description=(
        "Render the inline CTF fetch-result UI. First call ctf_fetch_url for one "
        "explicitly authorized URL, then pass its complete result here. This tool "
        "only displays supplied data and never sends an HTTP request."
    ),
    annotations={
        "title": "Show CTF fetch result",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    app=AppConfig(resource_uri=CTF_FETCH_RESULT_WIDGET_URI),
)
def ctf_render_fetch_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a prior CTF fetch result unchanged for the MCP App UI to render."""
    return result
