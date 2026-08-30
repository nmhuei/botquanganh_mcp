"""Bounded, thread-safe Center event inbox with dedup/coalescing."""

from __future__ import annotations

from collections import deque
import threading
from typing import Callable

from app.cli.center.events import Event, OperationObserved, RuntimeSnapshotReceived


class BoundedEventInbox:
    """Bound memory while protecting terminal and control events.

    Coalescable events replace an older queued event with the same key.
    Low-value events may be dropped when full. Other events raise no exception:
    the oldest coalescable/low-value event is evicted first.
    """

    def __init__(
        self,
        maxsize: int = 4096,
        *,
        dedup_limit: int = 8192,
        on_duplicate: Callable[[], None] | None = None,
        on_coalesced: Callable[[], None] | None = None,
        on_dropped: Callable[[], None] | None = None,
    ) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize = maxsize
        self._items: deque[Event] = deque()
        self._lock = threading.Lock()
        self._recent_ids: deque[str] = deque()
        self._recent_id_set: set[str] = set()
        self._dedup_limit = max(1, dedup_limit)
        self.on_duplicate = on_duplicate
        self.on_coalesced = on_coalesced
        self.on_dropped = on_dropped
        self.high_watermark = 0

    @staticmethod
    def _coalesce_key(event: Event) -> tuple[str, str] | None:
        if isinstance(event, RuntimeSnapshotReceived):
            return ("runtime", "snapshot")
        if isinstance(event, OperationObserved) and event.status == "running":
            if event.operation_id:
                return ("operation-running", event.operation_id)
        return None

    @staticmethod
    def _low_value(event: Event) -> bool:
        return isinstance(event, RuntimeSnapshotReceived)

    def _remember_id(self, event_id: str) -> None:
        if not event_id:
            return
        self._recent_ids.append(event_id)
        self._recent_id_set.add(event_id)
        while len(self._recent_ids) > self._dedup_limit:
            oldest = self._recent_ids.popleft()
            self._recent_id_set.discard(oldest)

    def put(self, event: Event) -> bool:
        with self._lock:
            event_id = str(getattr(event, "event_id", "") or "")
            if event_id and event_id in self._recent_id_set:
                if self.on_duplicate:
                    self.on_duplicate()
                return False

            key = self._coalesce_key(event)
            if key is not None:
                for index in range(len(self._items) - 1, -1, -1):
                    if self._coalesce_key(self._items[index]) == key:
                        self._items[index] = event
                        self._remember_id(event_id)
                        if self.on_coalesced:
                            self.on_coalesced()
                        return True

            if len(self._items) >= self.maxsize:
                drop_index = next(
                    (
                        index
                        for index, queued in enumerate(self._items)
                        if self._coalesce_key(queued) is not None or self._low_value(queued)
                    ),
                    None,
                )
                if drop_index is None:
                    if self._low_value(event):
                        if self.on_dropped:
                            self.on_dropped()
                        return False
                    # Preserve the newest critical event by evicting the oldest.
                    self._items.popleft()
                else:
                    del self._items[drop_index]
                if self.on_dropped:
                    self.on_dropped()

            self._items.append(event)
            self._remember_id(event_id)
            self.high_watermark = max(self.high_watermark, len(self._items))
            return True

    def drain(self, limit: int = 500) -> list[Event]:
        if limit <= 0:
            return []
        with self._lock:
            count = min(limit, len(self._items))
            return [self._items.popleft() for _ in range(count)]

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
