from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from typing import Any, Callable


_LOCK = threading.Lock()
_IN_FLIGHT: dict[str, threading.Event] = {}
_CACHE: dict[str, tuple[float, Any]] = {}


def stable_key(tool_name: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{tool_name}:{hashlib.sha256(encoded).hexdigest()}"


def run_once(key: str, ttl_seconds: float, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        _purge_locked(now)
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return _mark_cached(cached[1], key)

        event = _IN_FLIGHT.get(key)
        if event is None:
            event = threading.Event()
            _IN_FLIGHT[key] = event
            owner = True
        else:
            owner = False

    if not owner:
        event.wait()
        with _LOCK:
            cached = _CACHE.get(key)
            if cached:
                return _mark_cached(cached[1], key)
        return {
            "ok": False,
            "error": {
                "code": "IDEMPOTENCY_RESULT_MISSING",
                "message": "Duplicate request waited for an in-flight execution, but no result was cached.",
                "details": {"idempotency_key": key},
                "suggestion": "Retry once; if this persists, inspect server logs for the original execution.",
            },
        }

    try:
        result = fn()
        with _LOCK:
            _CACHE[key] = (time.monotonic() + ttl_seconds, copy.deepcopy(result))
        return result
    finally:
        with _LOCK:
            _IN_FLIGHT.pop(key, None)
            event.set()


def _mark_cached(result: Any, key: str) -> dict[str, Any]:
    cloned = copy.deepcopy(result)
    if isinstance(cloned, dict):
        cloned["idempotency_cache_hit"] = True
        cloned["idempotency_key"] = key
    return cloned


def _purge_locked(now: float) -> None:
    expired = [key for key, (expires_at, _) in _CACHE.items() if expires_at <= now]
    for key in expired:
        _CACHE.pop(key, None)
