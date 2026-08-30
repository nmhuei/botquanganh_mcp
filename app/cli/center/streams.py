"""SSE reconnect/backoff helpers independent from network implementation."""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class ReconnectBackoff:
    initial_seconds: float = 0.5
    maximum_seconds: float = 30.0
    jitter_ratio: float = 0.20
    attempt: int = 0

    def next_delay(self, *, jitter: bool = True) -> float:
        base = min(
            self.maximum_seconds,
            self.initial_seconds * (2 ** max(0, self.attempt)),
        )
        self.attempt += 1
        if not jitter or self.jitter_ratio <= 0:
            return base
        spread = base * self.jitter_ratio
        return max(0.0, base + random.uniform(-spread, spread))

    def reset(self) -> None:
        self.attempt = 0
