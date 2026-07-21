from __future__ import annotations

import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Deque, Tuple

from app.config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MAX_CLIENTS,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)


class SlidingWindowRateLimiter:
    """Bounded per-IP sliding-window rate limiter.

    Active client state is never silently evicted because that would reset a
    client's quota. Stale windows are pruned, and unseen clients are rejected
    conservatively when the configured client-state capacity is full.
    """

    def __init__(self):
        self.max_requests = RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = RATE_LIMIT_WINDOW_SECONDS
        self.max_clients = RATE_LIMIT_MAX_CLIENTS
        self._windows: OrderedDict[str, Deque[float]] = OrderedDict()
        self._lock = Lock()
        self._allowed_count = 0
        self._rejected_count = 0
        self._capacity_rejected_count = 0
        self._pruned_clients = 0

    def _prune_window(self, timestamps: Deque[float], window_start: float) -> None:
        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()

    def _prune_stale_clients(self, window_start: float) -> None:
        stale: list[str] = []
        for client_ip, timestamps in self._windows.items():
            self._prune_window(timestamps, window_start)
            if not timestamps:
                stale.append(client_ip)
        for client_ip in stale:
            self._windows.pop(client_ip, None)
        self._pruned_clients += len(stale)

    def is_allowed(self, client_ip: str) -> Tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)`` for a client."""
        if not RATE_LIMIT_ENABLED:
            return True, 0

        normalized_ip = str(client_ip or "unknown")[:256]
        now = time.monotonic()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._windows.get(normalized_ip)
            if timestamps is None:
                if len(self._windows) >= self.max_clients:
                    self._prune_stale_clients(window_start)
                if len(self._windows) >= self.max_clients:
                    self._rejected_count += 1
                    self._capacity_rejected_count += 1
                    return False, max(1, int(self.window_seconds))
                timestamps = deque()
                self._windows[normalized_ip] = timestamps
            else:
                self._windows.move_to_end(normalized_ip)

            self._prune_window(timestamps, window_start)
            if len(timestamps) >= self.max_requests:
                self._rejected_count += 1
                retry_after = int(timestamps[0] + self.window_seconds - now)
                return False, max(1, retry_after)

            timestamps.append(now)
            self._allowed_count += 1
            return True, 0

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "tracked_clients": len(self._windows),
                "max_clients": self.max_clients,
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "allowed": self._allowed_count,
                "rejected": self._rejected_count,
                "capacity_rejected": self._capacity_rejected_count,
                "pruned_clients": self._pruned_clients,
            }


rate_limiter = SlidingWindowRateLimiter()
