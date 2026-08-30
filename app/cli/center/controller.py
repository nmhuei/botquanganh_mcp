"""Canonical BQA Center state controller and render notification boundary."""

from __future__ import annotations

import time
from typing import Any, Callable

from app.cli.center.events import Event
from app.cli.center.inbox import BoundedEventInbox
from app.cli.center.reducer import reduce_event
from app.cli.center.state import CenterState


class CenterController:
    """Own canonical state, event inbox, reduction, and subscriber notifications."""

    def __init__(
        self,
        state: CenterState | None = None,
        *,
        inbox_size: int = 4096,
    ) -> None:
        self.state = state or CenterState()
        self._subscribers: list[Callable[[CenterState], None]] = []
        self.inbox = BoundedEventInbox(
            inbox_size,
            on_duplicate=self._duplicate,
            on_coalesced=self._coalesced,
            on_dropped=self._dropped,
        )
        self._last_render_started = 0.0

    def _duplicate(self) -> None:
        self.state.diagnostics.events_duplicate_total += 1

    def _coalesced(self) -> None:
        self.state.diagnostics.events_coalesced_total += 1

    def _dropped(self) -> None:
        self.state.diagnostics.events_dropped_total += 1

    def subscribe(self, callback: Callable[[CenterState], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[CenterState], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, event: Event) -> bool:
        accepted = self.inbox.put(event)
        self.state.diagnostics.queue_depth = len(self.inbox)
        self.state.diagnostics.queue_high_watermark = max(
            self.state.diagnostics.queue_high_watermark,
            self.inbox.high_watermark,
        )
        return accepted

    def dispatch(self, event: Event, *, notify: bool = True) -> CenterState:
        reduce_event(self.state, event)
        if notify:
            self.notify()
        return self.state

    def drain(self, limit: int = 500) -> int:
        events = self.inbox.drain(limit)
        for event in events:
            reduce_event(self.state, event)
        self.state.diagnostics.queue_depth = len(self.inbox)
        self.state.diagnostics.render_batch_size = len(events)
        return len(events)

    def notify(self) -> None:
        started = time.perf_counter()
        for callback in tuple(self._subscribers):
            callback(self.state)
        self.state.diagnostics.render_batch_count += 1
        self.state.diagnostics.render_duration_ms = (
            time.perf_counter() - started
        ) * 1000.0

    def drain_and_notify(self, limit: int = 500) -> int:
        processed = self.drain(limit)
        if processed:
            self.notify()
        return processed
