from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from threading import Lock


class MetricsTracker:
    """Thread-safe in-memory HTTP metrics with bounded latency history."""

    def __init__(self):
        self._lock = Lock()
        self._request_count = 0
        self._error_count = 0
        self._client_error_count = 0
        self._rate_limit_count = 0
        self._auth_failure_count = 0
        self._in_flight = 0
        self._peak_in_flight = 0
        self._latencies = deque(maxlen=1000)
        self._path_counts = defaultdict(int)
        self._status_counts = defaultdict(int)
        self._start_time = time.time()

    def begin_request(self) -> None:
        with self._lock:
            self._in_flight += 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)

    def record_request(
        self,
        path: str,
        latency_ms: float,
        status_code: int = 200,
    ) -> None:
        with self._lock:
            self._request_count += 1
            self._latencies.append(max(0.0, float(latency_ms)))
            self._path_counts[path] += 1
            self._status_counts[str(int(status_code))] += 1
            if self._in_flight > 0:
                self._in_flight -= 1
            if status_code == 429:
                self._rate_limit_count += 1
            if status_code in {401, 403}:
                self._auth_failure_count += 1
            if 400 <= status_code < 500:
                self._client_error_count += 1
            elif status_code >= 500:
                self._error_count += 1

    def record_rate_limit(self) -> None:
        """Backward-compatible direct counter for non-HTTP rate-limit events."""
        with self._lock:
            self._rate_limit_count += 1

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, math.ceil(percentile * len(ordered)) - 1)
        return ordered[index]

    def get_stats(self) -> dict:
        with self._lock:
            uptime = time.time() - self._start_time
            latencies = list(self._latencies)
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self._request_count,
                "error_count": self._error_count,
                "client_error_count": self._client_error_count,
                "auth_failures": self._auth_failure_count,
                "rate_limit_hits": self._rate_limit_count,
                "in_flight": self._in_flight,
                "peak_in_flight": self._peak_in_flight,
                "avg_latency_ms": round(avg_latency, 1),
                "p50_latency_ms": round(self._percentile(latencies, 0.50), 1),
                "p95_latency_ms": round(self._percentile(latencies, 0.95), 1),
                "path_counts": dict(self._path_counts),
                # Kept for compatibility with earlier health consumers.
                "tool_calls": dict(self._path_counts),
                "status_counts": dict(self._status_counts),
                "latency_sample_size": len(latencies),
                "started_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._start_time)
                ),
            }


metrics = MetricsTracker()
