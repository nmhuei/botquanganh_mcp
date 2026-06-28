import time
from collections import defaultdict
from typing import Tuple

from app.config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)


class SlidingWindowRateLimiter:
    """Per-IP sliding window rate limiter.

    Tracks request timestamps per client IP and rejects requests that exceed
    the configured limit within the rolling window.
    """

    def __init__(self):
        self.max_requests = RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = RATE_LIMIT_WINDOW_SECONDS
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> Tuple[bool, int]:
        """Check if request from client_ip is allowed.

        Returns (allowed: bool, retry_after_seconds: int).
        """
        if not RATE_LIMIT_ENABLED:
            return True, 0

        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries outside the window
        timestamps = self._windows[client_ip]
        self._windows[client_ip] = [t for t in timestamps if t > window_start]

        # Check limit
        if len(self._windows[client_ip]) >= self.max_requests:
            retry_after = int(
                self._windows[client_ip][0] + self.window_seconds - now
            )
            return False, max(1, retry_after)

        self._windows[client_ip].append(now)
        return True, 0


# Singleton instance
rate_limiter = SlidingWindowRateLimiter()
