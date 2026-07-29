from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


_PUBLIC_ERROR_CODES = {
    "INVALID_ARGUMENT",
    "RUNTIME_UNAVAILABLE",
    "RUN_NOT_FOUND",
    "AGENT_NOT_FOUND",
    "TASK_NOT_FOUND",
    "ARTIFACT_NOT_FOUND",
    "INVALID_STATE_TRANSITION",
    "BUDGET_EXCEEDED",
    "TOOL_PERMISSION_DENIED",
    "AUTHENTICATION_FAILED",
    "TIMEOUT",
    "INTERNAL_ERROR",
}
_RETRYABLE_STATUS_CODES = {502, 503, 504}
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


@dataclass(frozen=True)
class AgentRuntimeError(RuntimeError):
    """Normalized, public-safe failure returned by the agent runtime."""

    code: str
    message: str
    status_code: int | None = None
    retryable: bool = False
    request_id: str | None = None
    details: Any = None

    def __str__(self) -> str:
        return self.message


class AgentRuntimeClient:
    """Pooled asynchronous HTTP client for the BotQuangAnh Agent Runtime."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout_seconds: float = 30.0,
        result_timeout_seconds: float = 60.0,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        self._token = token.strip()
        self.timeout_seconds = self._validate_timeout(
            timeout_seconds, "timeout_seconds"
        )
        self.result_timeout_seconds = self._validate_timeout(
            result_timeout_seconds, "result_timeout_seconds"
        )
        if retry_attempts < 0 or retry_attempts > 5:
            raise ValueError("retry_attempts must be between 0 and 5")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout(self.timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=False,
        )
        self._closed = False

    @staticmethod
    def _validate_base_url(value: str) -> str:
        normalized = str(value).strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AGENT_RUNTIME_URL must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("AGENT_RUNTIME_URL cannot include credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("AGENT_RUNTIME_URL cannot include query or fragment")
        return normalized

    @staticmethod
    def _validate_timeout(value: float, name: str) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive number") from exc
        if normalized <= 0 or normalized > 600:
            raise ValueError(f"{name} must be greater than 0 and at most 600")
        return normalized

    @staticmethod
    def _timeout(seconds: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=min(seconds, 10.0),
            read=seconds,
            write=seconds,
            pool=min(seconds, 10.0),
        )

    def __repr__(self) -> str:
        return f"AgentRuntimeClient(base_url={self.base_url!r}, closed={self._closed})"

    @property
    def is_closed(self) -> bool:
        return self._closed or self._client.is_closed

    async def __aenter__(self) -> AgentRuntimeClient:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    def _headers(
        self,
        *,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Request-ID": request_id or str(uuid4()),
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _sanitize_message(self, message: str) -> str:
        sanitized = _BEARER_RE.sub("Bearer [REDACTED]", message)
        if self._token:
            sanitized = sanitized.replace(self._token, "[REDACTED]")
        return sanitized[:4096] or "Agent runtime request failed."

    @staticmethod
    def _request_id(response: httpx.Response, body: Any) -> str | None:
        header = response.headers.get("x-request-id") or response.headers.get(
            "x-correlation-id"
        )
        if header:
            return header
        if isinstance(body, Mapping):
            value = body.get("request_id") or body.get("correlation_id")
            if value:
                return str(value)
            error = body.get("error")
            if isinstance(error, Mapping):
                value = error.get("request_id") or error.get("correlation_id")
                if value:
                    return str(value)
        return None

    @staticmethod
    def _infer_code(status_code: int, path: str) -> str:
        if status_code in {408, 504}:
            return "TIMEOUT"
        if status_code == 401:
            return "AUTHENTICATION_FAILED"
        if status_code == 403:
            return "TOOL_PERMISSION_DENIED"
        if status_code == 404:
            if "/runs/" in path:
                return "RUN_NOT_FOUND"
            if "/agents/" in path:
                return "AGENT_NOT_FOUND"
            if "/tasks/" in path:
                return "TASK_NOT_FOUND"
            if "/artifacts/" in path:
                return "ARTIFACT_NOT_FOUND"
        if status_code == 409:
            return "INVALID_STATE_TRANSITION"
        if status_code == 429:
            return "BUDGET_EXCEEDED"
        if status_code in {502, 503}:
            return "RUNTIME_UNAVAILABLE"
        if status_code in {400, 422}:
            return "INVALID_ARGUMENT"
        return "INTERNAL_ERROR"

    def _normalize_http_error(
        self, response: httpx.Response, path: str
    ) -> AgentRuntimeError:
        try:
            body: Any = response.json()
        except ValueError:
            body = None

        error_body: Mapping[str, Any] = {}
        if isinstance(body, Mapping):
            nested = body.get("error")
            if isinstance(nested, Mapping):
                error_body = nested
            else:
                error_body = body

        raw_code = error_body.get("code")
        inferred_code = self._infer_code(response.status_code, path)
        code = str(raw_code) if raw_code else inferred_code
        if code not in _PUBLIC_ERROR_CODES:
            code = inferred_code

        raw_message = error_body.get("message")
        message = self._sanitize_message(
            str(raw_message)
            if raw_message
            else f"Agent runtime returned HTTP {response.status_code}."
        )
        retryable = bool(error_body.get("retryable")) or response.status_code in (
            _RETRYABLE_STATUS_CODES | {408, 429}
        )
        details = error_body.get("details")
        return AgentRuntimeError(
            code=code,
            message=message,
            status_code=response.status_code,
            retryable=retryable,
            request_id=self._request_id(response, body),
            details=details,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        if self.is_closed:
            raise AgentRuntimeError(
                code="RUNTIME_UNAVAILABLE",
                message="Agent runtime client is closed.",
                retryable=False,
            )

        normalized_method = method.upper()
        attempts = 1 + (self.retry_attempts if normalized_method == "GET" else 0)
        timeout = self._timeout(timeout_seconds or self.timeout_seconds)
        headers = self._headers(
            request_id=request_id, idempotency_key=idempotency_key
        )

        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    normalized_method,
                    path,
                    json=json,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
            except httpx.TimeoutException as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise AgentRuntimeError(
                    code="TIMEOUT",
                    message="Agent runtime request timed out.",
                    retryable=True,
                ) from exc
            except httpx.TransportError as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise AgentRuntimeError(
                    code="RUNTIME_UNAVAILABLE",
                    message="Agent runtime is unavailable.",
                    retryable=True,
                ) from exc

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt + 1 < attempts:
                await asyncio.sleep(self.retry_backoff_seconds * (attempt + 1))
                continue
            if not 200 <= response.status_code < 300:
                raise self._normalize_http_error(response, path)
            if response.status_code == 204 or not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise AgentRuntimeError(
                    code="INTERNAL_ERROR",
                    message="Agent runtime returned an invalid JSON response.",
                    status_code=response.status_code,
                    retryable=False,
                    request_id=response.headers.get("x-request-id"),
                ) from exc

        raise AgentRuntimeError(
            code="RUNTIME_UNAVAILABLE",
            message="Agent runtime is unavailable.",
            retryable=True,
        )

    async def health(self) -> Any:
        return await self._request("GET", "/health")

    async def readiness(self) -> Any:
        return await self._request("GET", "/ready")

    async def create_run(
        self, payload: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> Any:
        return await self._request(
            "POST",
            "/v1/runs",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def get_run(self, run_id: str) -> Any:
        return await self._request("GET", f"/v1/runs/{run_id}")

    async def get_run_events(
        self, run_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> Any:
        return await self._request(
            "GET",
            f"/v1/runs/{run_id}/events",
            params={"after_sequence": after_sequence, "limit": limit},
        )

    async def send_run_message(
        self,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/v1/runs/{run_id}/messages",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def cancel_run(
        self,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/v1/runs/{run_id}/cancel",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def get_run_result(self, run_id: str) -> Any:
        return await self._request(
            "GET",
            f"/v1/runs/{run_id}/result",
            timeout_seconds=self.result_timeout_seconds,
        )

    async def list_agents(
        self,
        *,
        run_id: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> Any:
        params: dict[str, Any] = {"limit": limit}
        if run_id:
            params["run_id"] = run_id
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/v1/agents", params=params)

    async def get_agent(self, agent_id: str) -> Any:
        return await self._request("GET", f"/v1/agents/{agent_id}")

    async def send_agent_message(
        self,
        agent_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/v1/agents/{agent_id}/messages",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def cancel_agent(
        self,
        agent_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/v1/agents/{agent_id}/cancel",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def get_task(self, task_id: str) -> Any:
        return await self._request("GET", f"/v1/tasks/{task_id}")

    async def retry_task(
        self,
        task_id: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            f"/v1/tasks/{task_id}/retry",
            json=payload,
            idempotency_key=idempotency_key,
        )

    async def get_artifact(
        self,
        artifact_id: str,
        *,
        include_content: bool = False,
        offset: int = 0,
        limit: int = 262_144,
    ) -> Any:
        path = f"/v1/artifacts/{artifact_id}"
        params: Mapping[str, Any] | None = None
        if include_content:
            path += "/content"
            params = {"offset": offset, "limit": limit}
        return await self._request("GET", path, params=params)
