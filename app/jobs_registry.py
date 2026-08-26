"""Thread-safe in-memory registry for long-running host operations."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

JOB_STATUSES = ("queued", "running", "done", "error")
FINISHED_STATUSES = ("done", "error")
MAX_RECORDS = 512

_DETAIL_MAX_CHARS = 400
_EXCERPT_MAX_CHARS = 2000


@dataclass
class JobRecord:
    job_id: str
    op: str
    chat_id: str | None = None
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    detail: str = ""
    result_excerpt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "op": self.op,
            "chat_id": self.chat_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "detail": self.detail,
            "result_excerpt": self.result_excerpt,
        }


class JobsRegistry:
    """Bounded store of operation records; records are shared and read-only
    outside the registry's own lock."""

    def __init__(self, max_records: int = MAX_RECORDS) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, JobRecord] = {}
        self._max_records = max(1, int(max_records))

    def register(self, op: str, chat_id: str | None = None) -> JobRecord:
        record = JobRecord(job_id=uuid.uuid4().hex, op=str(op), chat_id=chat_id)
        with self._lock:
            self._records[record.job_id] = record
            self._evict_over_capacity_locked()
        return record

    def start(self, job_id: str) -> bool:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return False
            record.status = "running"
            if record.started_at is None:
                record.started_at = time.time()
            return True

    def finish(
        self,
        job_id: str,
        ok: bool,
        detail: str = "",
        result_excerpt: str | None = None,
    ) -> bool:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return False
            record.status = "done" if ok else "error"
            record.finished_at = time.time()
            record.detail = str(detail)[:_DETAIL_MAX_CHARS]
            record.result_excerpt = (
                str(result_excerpt)[:_EXCERPT_MAX_CHARS]
                if result_excerpt is not None
                else None
            )
            return True

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def list(
        self,
        chat_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        if status is not None and status not in JOB_STATUSES:
            raise ValueError(
                f"Unknown job status '{status}'; expected one of: "
                + ", ".join(JOB_STATUSES)
            )
        bounded_limit = max(0, int(limit))
        with self._lock:
            records = [
                record
                for record in reversed(tuple(self._records.values()))
                if (chat_id is None or record.chat_id == chat_id)
                and (status is None or record.status == status)
            ]
        return records[:bounded_limit]

    def _evict_over_capacity_locked(self) -> None:
        while len(self._records) > self._max_records:
            victim_id = next(
                (
                    job_id
                    for job_id, record in self._records.items()
                    if record.status in FINISHED_STATUSES
                ),
                None,
            )
            if victim_id is None:
                victim_id = next(iter(self._records))
            del self._records[victim_id]


_registry: JobsRegistry | None = None
_registry_lock = threading.Lock()


def get_jobs_registry() -> JobsRegistry:
    global _registry
    registry = _registry
    if registry is None:
        with _registry_lock:
            registry = _registry
            if registry is None:
                registry = JobsRegistry()
                _registry = registry
    return registry
