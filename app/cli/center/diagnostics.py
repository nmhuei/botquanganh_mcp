"""Small runtime counters for BQA Center internals."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.cli.center.state import CenterState


def diagnostics_snapshot(state: CenterState) -> dict[str, Any]:
    data = asdict(state.diagnostics)
    data.update(
        {
            "sessions_count": len(state.sessions.by_id),
            "operations_cached": len(state.operations.by_id),
            "logs_cached": len(state.logs.by_id),
            "stream_phase": state.stream.phase.value,
            "stream_last_event_id": state.stream.last_event_id,
            "selected_session": state.sessions.selected_id,
        }
    )
    return data
