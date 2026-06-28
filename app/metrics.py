import time
from collections import defaultdict, deque
from threading import Lock


class MetricsTracker:
    """Thread-safe in-memory metrics tracker for request monitoring."""

    def __init__(self):
        self._lock = Lock()
        self._request_count = 0
        self._error_count = 0
        self._rate_limit_count = 0
        self._latencies = deque(maxlen=1000)
        self._tool_calls = defaultdict(int)
        self._start_time = time.time()

    def record_request(self, tool_name: str, latency_ms: float, status_code: int = 200):
        with self._lock:
            self._request_count += 1
            self._latencies.append(latency_ms)
            self._tool_calls[tool_name] += 1
            if status_code == 429:
                self._rate_limit_count += 1
            elif status_code >= 500:
                self._error_count += 1

    def record_rate_limit(self):
        with self._lock:
            self._rate_limit_count += 1

    def get_stats(self) -> dict:
        with self._lock:
            uptime = time.time() - self._start_time
            latencies = list(self._latencies)
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self._request_count,
                "error_count": self._error_count,
                "rate_limit_hits": self._rate_limit_count,
                "avg_latency_ms": round(avg_latency, 1),
                "tool_calls": dict(self._tool_calls),
                "started_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._start_time)
                ),
            }


metrics = MetricsTracker()
