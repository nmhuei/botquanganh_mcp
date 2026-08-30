"""Tk main-loop scheduler for bounded event reduction/render batches."""

from __future__ import annotations

import time
from typing import Any, Callable


class TkRenderScheduler:
    """Coalesce render requests and keep each Tk tick within a time budget."""

    def __init__(
        self,
        root: Any,
        *,
        drain: Callable[[int], int],
        render: Callable[[], None],
        max_events_per_tick: int = 500,
        budget_ms: float = 8.0,
    ) -> None:
        self.root = root
        self.drain = drain
        self.render = render
        self.max_events_per_tick = max_events_per_tick
        self.budget_ms = budget_ms
        self._scheduled = False
        self.closed = False

    def request(self, queue_depth: int = 1) -> None:
        if self.closed or self._scheduled:
            return
        self._scheduled = True
        if queue_depth <= 20:
            self.root.after_idle(self._tick)
        elif queue_depth <= 200:
            self.root.after(20, self._tick)
        else:
            self.root.after(1, self._tick)

    def _tick(self) -> None:
        self._scheduled = False
        if self.closed:
            return
        started = time.perf_counter()
        processed_total = 0
        while processed_total < self.max_events_per_tick:
            processed = self.drain(min(100, self.max_events_per_tick - processed_total))
            processed_total += processed
            if processed == 0:
                break
            if (time.perf_counter() - started) * 1000.0 >= self.budget_ms:
                break
        self.render()
        if processed_total >= self.max_events_per_tick:
            self.request(201)

    def close(self) -> None:
        self.closed = True
