"""Typed search outcomes, counters, and limit reasons."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SearchLimitReason(str, Enum):
    """Machine-readable reason a search stopped early."""

    DEADLINE = "deadline"
    WORK_MATCHES = "work_matches"
    SCANNED_FILES = "scanned_files"
    SCANNED_BYTES = "scanned_bytes"
    PAYLOAD = "payload"
    RESULT_CAP = "result_cap"
    QUEUE = "queue"


class SearchEngine(str, Enum):
    """Search execution engine."""

    RIPGREP = "ripgrep"
    PYTHON = "python"


class SearchMode(str, Enum):
    """Supported workspace search modes."""

    CONTENT = "content"
    PATH = "path"


@dataclass
class SearchCounters:
    """Safe numeric counters for one search execution."""

    scanned_files: int = 0
    scanned_bytes: int = 0
    candidate_matches: int = 0
    returned_matches: int = 0
    skipped_special_files: int = 0


@dataclass
class SearchOutcome:
    """Ordered engine result with completeness metadata."""

    ok: bool = True
    matches: list[Any] = field(default_factory=list)
    total_found: int = 0
    count_complete: bool = True
    limit_reason: SearchLimitReason | None = None
    counters: SearchCounters = field(default_factory=SearchCounters)
    engine: SearchEngine = SearchEngine.PYTHON
    error: dict[str, Any] | None = None

    @classmethod
    def partial(cls, reason: SearchLimitReason) -> SearchOutcome:
        """Build an empty partial outcome for an exhausted budget."""
        return cls(ok=True, matches=[], total_found=0, count_complete=False, limit_reason=reason)

    @classmethod
    def complete(
        cls,
        matches: list[Any],
        total_found: int,
        engine: SearchEngine,
        counters: SearchCounters | None = None,
    ) -> SearchOutcome:
        """Build a complete outcome with no truncation."""
        return cls(
            ok=True,
            matches=list(matches),
            total_found=total_found,
            count_complete=True,
            limit_reason=None,
            counters=counters or SearchCounters(),
            engine=engine,
        )
