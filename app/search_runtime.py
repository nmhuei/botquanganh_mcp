"""Deadline checks, process-group cleanup, and search admission."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

from app.error_contract import ServiceBusyError


def deadline_exceeded(deadline_monotonic: float | None) -> bool:
    """Return True when the monotonic deadline has passed."""
    if deadline_monotonic is None:
        return False
    return time.monotonic() >= deadline_monotonic


def deadline_from_timeout(timeout_seconds: float | None) -> float | None:
    """Convert a timeout into a monotonic deadline."""
    if timeout_seconds is None:
        return None
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError):
        return None
    if timeout <= 0:
        return time.monotonic()
    return time.monotonic() + timeout


def terminate_process_group(proc: subprocess.Popen) -> None:
    """Terminate a ripgrep process group without raising."""
    try:
        proc_pid = getattr(proc, "pid", None)
        if proc_pid is None:
            try:
                proc.kill()
            except (OSError, AttributeError):
                return
            return
        group_id = os.getpgid(proc_pid)
        os.killpg(group_id, signal.SIGKILL)
    except (OSError, ProcessLookupError, AttributeError):
        try:
            proc.kill()
        except (OSError, ProcessLookupError, AttributeError):
            return


def search_reap_timeout() -> float | None:
    """Return the configured child-reap grace period in seconds."""
    try:
        from app import config as config_module

        try:
            return max(0.0, float(config_module.HOST_TASK_KILL_GRACE_SECONDS))
        except (AttributeError, TypeError, ValueError):
            return max(0.0, float(config_module.SEARCH_TEXT_DEADLINE_SECONDS))
    except (AttributeError, TypeError, ValueError):
        return None


def _close_proc_streams(proc: subprocess.Popen) -> None:
    """Close child pipes without raising."""
    for stream in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
        try:
            if stream is not None:
                stream.close()
        except (OSError, ValueError):
            continue


def _proc_exited(proc: subprocess.Popen) -> bool:
    """Return True when the child has exited."""
    try:
        return proc.poll() is not None
    except (OSError, ValueError, AttributeError):
        return True


def reap_process(proc: subprocess.Popen, timeout_seconds: float | None = None) -> None:
    """Terminate and reap a child so no ripgrep process stays alive."""
    if timeout_seconds is None:
        timeout_seconds = search_reap_timeout()
    try:
        if timeout_seconds is None:
            proc.wait()
            _close_proc_streams(proc)
            return
        proc.wait(timeout=timeout_seconds)
        _close_proc_streams(proc)
        return
    except TypeError:
        try:
            proc.wait()
        except (OSError, ValueError, TypeError):
            pass
        _close_proc_streams(proc)
        return
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    if not _proc_exited(proc):
        terminate_process_group(proc)
    try:
        proc.wait(timeout=timeout_seconds)
    except TypeError:
        try:
            proc.wait()
        except (OSError, ValueError, TypeError):
            pass
    except (subprocess.TimeoutExpired, OSError, ValueError):
        try:
            proc.kill()
        except (OSError, ProcessLookupError, AttributeError):
            pass
        try:
            proc.wait()
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            pass
    _close_proc_streams(proc)


class SearchLease:
    """Idempotent handle for one admitted search slot."""

    def __init__(self, manager: SearchCapacity, chat_id: str | None) -> None:
        self._manager = manager
        self._chat_id = chat_id or ""
        self._released = False

    def release(self) -> None:
        """Release the slot exactly once."""
        if self._released:
            return
        self._released = True
        self._manager._release(self._chat_id)


class SearchCapacity:
    """Thread-safe global and per-chat admission for searches."""

    def __init__(self, global_limit: int, per_chat_limit: int, queue_timeout: float) -> None:
        if global_limit < 1:
            raise ValueError("global_limit must be >= 1.")
        if per_chat_limit < 1:
            raise ValueError("per_chat_limit must be >= 1.")
        if queue_timeout < 0:
            raise ValueError("queue_timeout must be >= 0.")
        self._global_limit = global_limit
        self._per_chat_limit = per_chat_limit
        self._queue_timeout = float(queue_timeout)
        self._condition = threading.Condition()
        self._active_global = 0
        self._active_per_chat: dict[str, int] = {}

    def _can_admit(self, chat_id: str) -> bool:
        if self._active_global >= self._global_limit:
            return False
        return self._active_per_chat.get(chat_id, 0) < self._per_chat_limit

    def acquire(self, chat_id: str | None) -> SearchLease:
        """Admit one search or raise ServiceBusyError after queue timeout."""
        key = str(chat_id or "")
        deadline = time.monotonic() + self._queue_timeout
        with self._condition:
            while not self._can_admit(key):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ServiceBusyError(
                        "Search capacity is unavailable; retry shortly."
                    )
                self._condition.wait(timeout=remaining)
            self._active_global += 1
            self._active_per_chat[key] = self._active_per_chat.get(key, 0) + 1
            return SearchLease(self, key)

    def sync_limits(self, global_limit: int, per_chat_limit: int, queue_timeout: float) -> None:
        """Refresh limits from configuration without dropping active counts."""
        if global_limit < 1:
            raise ValueError("global_limit must be >= 1.")
        if per_chat_limit < 1:
            raise ValueError("per_chat_limit must be >= 1.")
        if queue_timeout < 0:
            raise ValueError("queue_timeout must be >= 0.")
        with self._condition:
            self._global_limit = global_limit
            self._per_chat_limit = per_chat_limit
            self._queue_timeout = float(queue_timeout)
            self._condition.notify_all()

    def snapshot(self) -> dict[str, float]:
        """Return current limits and usage for observability."""
        with self._condition:
            return {
                "global_limit": float(self._global_limit),
                "per_chat_limit": float(self._per_chat_limit),
                "queue_timeout": float(self._queue_timeout),
                "active_global": float(self._active_global),
            }

    def _release(self, chat_id: str) -> None:
        with self._condition:
            self._active_global = max(0, self._active_global - 1)
            current = self._active_per_chat.get(chat_id, 0)
            if current <= 1:
                self._active_per_chat.pop(chat_id, None)
            else:
                self._active_per_chat[chat_id] = current - 1
            self._condition.notify_all()


_SHARED_CAPACITY: SearchCapacity | None = None
_SHARED_CAPACITY_LOCK = threading.Lock()


def default_search_capacity() -> SearchCapacity:
    """Return the shared admission manager synced to current configuration."""
    from app import config as config_module

    global _SHARED_CAPACITY
    global_limit = int(config_module.WORKSPACE_SEARCH_MAX_CONCURRENT)
    per_chat_limit = int(config_module.WORKSPACE_SEARCH_MAX_PER_CHAT)
    queue_timeout = float(config_module.WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS)
    with _SHARED_CAPACITY_LOCK:
        if _SHARED_CAPACITY is None:
            _SHARED_CAPACITY = SearchCapacity(
                global_limit=global_limit,
                per_chat_limit=per_chat_limit,
                queue_timeout=queue_timeout,
            )
        else:
            _SHARED_CAPACITY.sync_limits(global_limit, per_chat_limit, queue_timeout)
        return _SHARED_CAPACITY


def reset_search_capacity_for_tests() -> None:
    """Drop the shared manager so tests start from a clean admission state."""
    global _SHARED_CAPACITY
    with _SHARED_CAPACITY_LOCK:
        _SHARED_CAPACITY = None
