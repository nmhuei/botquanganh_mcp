from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from app.cli.errors import (
    CLIError,
    ConnectionCLIError,
    TimeoutCLIError,
    error_from_http,
)


@dataclass(slots=True)
class HTTPResult:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.text())
        except json.JSONDecodeError as exc:
            raise CLIError(
                f"Server returned invalid JSON (HTTP {self.status}).",
                details={"preview": self.text()[:500]},
            ) from exc


class RESTClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 15.0):
        normalized = base_url.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise CLIError("REST base URL must use http:// or https:// with a host.")
        if parsed.username or parsed.password:
            raise CLIError("Credentials must not be embedded in the REST base URL.")
        if parsed.query or parsed.fragment:
            raise CLIError("REST base URL must not contain a query string or fragment.")
        self.base_url = normalized
        self.token = token
        self.timeout = timeout

    def _headers(self, *, json_body: bool = False, accept: str = "application/json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "bqa-cli/1.0",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def raw_request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any = None,
        accept: str = "application/json",
    ) -> HTTPResult:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized_path}"
        if query:
            filtered = {key: value for key, value in query.items() if value is not None}
            if filtered:
                url = f"{url}?{urlencode(filtered, doseq=True)}"
        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method.upper(),
            headers=self._headers(json_body=json_body is not None, accept=accept),
        )
        try:
            # Schemes, host, embedded credentials, query, and fragment are
            # validated in __init__ before this request is constructed.
            with urlopen(request, timeout=self.timeout) as response:  # nosec B310
                return HTTPResult(
                    status=int(response.status),
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return HTTPResult(
                status=int(exc.code),
                headers=dict(exc.headers.items()) if exc.headers else {},
                body=exc.read(),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutCLIError(f"Request timed out after {self.timeout:g}s: {url}") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise TimeoutCLIError(f"Request timed out after {self.timeout:g}s: {url}") from exc
            raise ConnectionCLIError(f"Unable to connect to {self.base_url}: {reason}") from exc
        except OSError as exc:
            raise ConnectionCLIError(f"Unable to connect to {self.base_url}: {exc}") from exc

    @staticmethod
    def _message(payload: Any, status: int) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or f"HTTP {status}")
            if payload.get("detail"):
                return str(payload["detail"])
            if payload.get("message"):
                return str(payload["message"])
        return f"Request failed with HTTP {status}."

    @staticmethod
    def _is_command_result(payload: Any) -> bool:
        return (
            isinstance(payload, dict)
            and "exit_code" in payload
            and "stdout" in payload
            and "stderr" in payload
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        json_body: Any = None,
        allow_command_failure: bool = False,
    ) -> Any:
        result = self.raw_request(method, path, query=query, json_body=json_body)
        payload = result.json()
        if 200 <= result.status < 300:
            return payload
        if allow_command_failure and self._is_command_result(payload):
            return payload
        raise error_from_http(result.status, self._message(payload, result.status), payload)

    def get(self, path: str, *, query: Mapping[str, Any] | None = None) -> Any:
        return self.request_json("GET", path, query=query)

    def post(self, path: str, *, json_body: Any = None, allow_command_failure: bool = False) -> Any:
        return self.request_json(
            "POST", path, json_body=json_body, allow_command_failure=allow_command_failure
        )

    def put(self, path: str, *, json_body: Any = None) -> Any:
        return self.request_json("PUT", path, json_body=json_body)

    def patch(self, path: str, *, json_body: Any = None) -> Any:
        return self.request_json("PATCH", path, json_body=json_body)
