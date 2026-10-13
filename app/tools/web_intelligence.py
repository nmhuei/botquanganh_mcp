"""Unified web intelligence tool: unrestricted HTTP/HTTPS fetching, clean text conversion, and CTF recon.

Consolidates web request execution and result parsing into an evolved super-tool.
Adheres to the user's maximum-freedom policy (permits HTTP/HTTPS, localhost, 127.0.0.1, LAN IP)
while automatically detecting hidden HTML comments, hidden form fields, and CTF flag patterns.
Preserves UI widget compatibility with CTF_FETCH_RESULT_WIDGET_URI.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import httpx
from fastmcp.apps import AppConfig

from app.mcp_server import mcp
from app.security import format_error_response
from app.tools_common import (
    _begin_workspace_journal,
    _finish_workspace_journal,
    _guard_chat_id,
    _record_tool_call,
    enforce_bridge_payload_limit,
)
from app.ui.ctf_fetch_result import CTF_FETCH_RESULT_WIDGET_URI

_DEFAULT_TIMEOUT_SECONDS = 15
_DEFAULT_MAX_BYTES = 1_048_576  # 1 MB
_MAX_ALLOWED_BYTES = 10_485_760  # 10 MB
_USER_AGENT = "BotQuangAnh-WebIntelligence/2.0"

_FLAG_PATTERNS = [
    re.compile(r"flag\{[^}\s]+\}", re.IGNORECASE),
    re.compile(r"ctf\{[^}\s]+\}", re.IGNORECASE),
    re.compile(r"picoctf\{[^}\s]+\}", re.IGNORECASE),
    re.compile(r"htb\{[^}\s]+\}", re.IGNORECASE),
    re.compile(r"bqa\{[^}\s]+\}", re.IGNORECASE),
]

_SENSITIVE_HEADER_KEYS = {
    "server",
    "x-powered-by",
    "x-aspnet-version",
    "x-generator",
    "via",
    "set-cookie",
}


class _HTMLIntelligenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.comments: list[str] = []
        self.hidden_inputs: list[dict[str, str]] = []
        self.meta_tags: dict[str, str] = {}
        self.text_parts: list[str] = []
        self._in_ignored_tag = False
        self._ignored_tags = {"script", "style", "noscript"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignored_tags:
            self._in_ignored_tag = True
            return

        attr_dict = {k.lower(): v or "" for k, v in attrs}

        if tag_lower == "input" and attr_dict.get("type", "").lower() == "hidden":
            self.hidden_inputs.append(
                {
                    "name": attr_dict.get("name", ""),
                    "value": attr_dict.get("value", ""),
                    "id": attr_dict.get("id", ""),
                }
            )

        if tag_lower == "meta":
            key = attr_dict.get("name") or attr_dict.get("property") or attr_dict.get("http-equiv")
            content = attr_dict.get("content")
            if key and content:
                self.meta_tags[key] = content

        if tag_lower in {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._ignored_tags:
            self._in_ignored_tag = False

    def handle_comment(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.comments.append(cleaned)

    def handle_data(self, data: str) -> None:
        if not self._in_ignored_tag:
            self.text_parts.append(data)


def _extract_flags(text: str) -> list[str]:
    found: set[str] = set()
    for pattern in _FLAG_PATTERNS:
        for match in pattern.findall(text):
            found.add(match)
    return sorted(found)


def _parse_html_intelligence(raw_html: str) -> tuple[str, dict[str, Any]]:
    parser = _HTMLIntelligenceParser()
    try:
        parser.feed(raw_html)
    except Exception:
        pass

    raw_text = "".join(parser.text_parts)
    clean_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    plain_text = "\n".join(clean_lines)

    intel = {
        "comments": parser.comments[:50],
        "hidden_inputs": parser.hidden_inputs[:50],
        "meta": parser.meta_tags,
    }
    return plain_text, intel


def _fetch_url(
    client: httpx.Client, method: str, url: str, max_bytes: int
) -> tuple[httpx.Response, bytes, bool]:
    """Read a bounded response body and close the stream on overflow."""
    body = bytearray()
    truncated = False
    with client.stream(method, url) as response:
        for chunk in response.iter_bytes():
            remaining = max_bytes - len(body)
            body.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
                break
    return response, bytes(body), truncated


@mcp.tool(
    name="web_intelligence",
    description=(
        "Unified web intelligence super-tool. Fetches HTTP and HTTPS resources with zero "
        "arbitrary network restrictions (supports localhost, 127.0.0.1, LAN targets for CTF/dev). "
        "Automatically parses HTML into clean markdown/text and extracts reconnaissance clues "
        "including comments, hidden form fields, server headers, and CTF flags. "
        "Requires an attributable chat_id in enforce mode."
    ),
    app=AppConfig(resource_uri=CTF_FETCH_RESULT_WIDGET_URI),
)
def web_intelligence(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    follow_redirects: bool = True,
    chat_id: Optional[str] = None,
    intent: Optional[str] = None,
) -> dict[str, Any]:
    """Execute unbounded network reconnaissance and intelligent web content analysis."""
    validated, rejection = _guard_chat_id("web_intelligence", chat_id)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "web_intelligence")

    journal_details = {"url": url, "method": method}
    if intent:
        journal_details["intent"] = str(intent).strip()[:300]
    journal_op = _begin_workspace_journal("web_intelligence", validated, journal_details)

    try:
        parsed_url = urlsplit(url)
        if not parsed_url.scheme or parsed_url.scheme.lower() not in {"http", "https"}:
            result = {
                "ok": False,
                "error": {
                    "code": "INVALID_URL",
                    "message": "URL must explicitly start with http:// or https://",
                },
            }
            _finish_workspace_journal("web_intelligence", validated, journal_op, ok=False, details=journal_details)
            return enforce_bridge_payload_limit(result, "web_intelligence")

        req_headers = {"User-Agent": _USER_AGENT}
        if headers:
            req_headers.update(headers)

        bounded_max_bytes = max(1024, min(max_bytes, _MAX_ALLOWED_BYTES))
        effective_timeout = max(1, min(timeout_seconds, 60))

        with httpx.Client(
            verify=False,
            follow_redirects=follow_redirects,
            timeout=httpx.Timeout(effective_timeout),
            headers=req_headers,
        ) as client:
            response, raw_bytes, truncated = _fetch_url(
                client, method.upper(), url, bounded_max_bytes
            )

        content_type = response.headers.get("content-type", "")
        body_text = raw_bytes.decode("utf-8", errors="replace")

        is_html = "html" in content_type.lower() or "<html" in body_text[:500].lower()
        if is_html:
            clean_text, html_intel = _parse_html_intelligence(body_text)
        else:
            clean_text = body_text
            html_intel = {"comments": [], "hidden_inputs": [], "meta": {}}

        # Flag extraction across both raw body and comments
        all_text_for_flags = body_text + "\n" + "\n".join(html_intel.get("comments", []))
        detected_flags = _extract_flags(all_text_for_flags)

        sensitive_headers = {
            k: v for k, v in response.headers.items() if k.lower() in _SENSITIVE_HEADER_KEYS
        }

        result = {
            "ok": True,
            "status_code": response.status_code,
            "url": str(response.url),
            "content_type": content_type,
            "body": clean_text[:100_000],
            "raw_body_sample": body_text[:2000],
            "body_truncated": truncated,
            "bytes_received": len(raw_bytes),
            "intelligence": {
                "flags": detected_flags,
                "comments": html_intel["comments"],
                "hidden_inputs": html_intel["hidden_inputs"],
                "meta": html_intel["meta"],
                "headers": sensitive_headers,
            },
            "widget_uri": CTF_FETCH_RESULT_WIDGET_URI,
        }
    except Exception as exc:
        result = format_error_response(exc)

    _record_tool_call("web_intelligence", validated)
    finish_details = dict(journal_details)
    if isinstance(result, dict) and result.get("ok"):
        finish_details["status_code"] = result.get("status_code")
        finish_details["bytes_received"] = result.get("bytes_received")
        finish_details["content_type"] = result.get("content_type")
        finish_details["stdout"] = result.get("body", "")[:5000]

    _finish_workspace_journal(
        "web_intelligence",
        validated,
        journal_op,
        ok=isinstance(result, dict) and bool(result.get("ok", False)),
        details=finish_details,
    )
    return enforce_bridge_payload_limit(result, "web_intelligence")
