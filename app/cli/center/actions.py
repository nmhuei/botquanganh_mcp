"""Central action concurrency rules for BQA Center."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
import uuid
from typing import Any, Callable

from app.cli.center.events import ActionFinished, ActionRequested, ActionStarted


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    group: str
    work: Callable[[], dict[str, Any]]


class ActionController:
    """Run finite actions off the Tk thread with duplicate/conflict protection."""

    def __init__(self, emit: Callable[[Any], None]) -> None:
        self.emit = emit
        self._lock = threading.Lock()
        self._running_by_group: dict[str, str] = {}

    def running(self, group: str) -> bool:
        with self._lock:
            return group in self._running_by_group

    def request(self, spec: ActionSpec) -> str | None:
        with self._lock:
            if spec.group in self._running_by_group:
                return None
            action_id = uuid.uuid4().hex
            self._running_by_group[spec.group] = action_id

        self.emit(
            ActionRequested(
                action_id=action_id,
                kind=spec.kind,
                group=spec.group,
            )
        )

        def runner() -> None:
            started = time.monotonic()
            self.emit(ActionStarted(action_id=action_id, observed_at=started))
            ok = False
            message = ""
            error = ""
            try:
                result = spec.work() or {}
                ok = bool(result.get("ok", True))
                message = str(result.get("message") or "")
                if not ok:
                    error = str(result.get("error") or message or "action failed")
            except Exception as exc:
                error = str(exc)
            finally:
                finished = time.monotonic()
                self.emit(
                    ActionFinished(
                        action_id=action_id,
                        ok=ok,
                        observed_at=finished,
                        message=message,
                        error=error,
                    )
                )
                with self._lock:
                    self._running_by_group.pop(spec.group, None)

        threading.Thread(
            target=runner,
            daemon=True,
            name=f"bqa-center-action-{spec.kind}",
        ).start()
        return action_id
