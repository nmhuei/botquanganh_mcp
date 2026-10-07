"""Provide asynchronous process task management."""

from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Deque

from app import config


DEFAULT_RING_SIZE = 1000
DEFAULT_LOG_DIR = Path.home() / "Downloads" / "bqa-trash" / "task-logs"
STAT_START_FIELD = 22
BYTES_PER_KIB = 1024
READ_CHUNK_SIZE = 4096
TERM_SIGNAL_GRACE = getattr(config, "HOST_TASK_KILL_GRACE_SECONDS", 3)
MAX_TASKS_PER_CHAT = getattr(config, "HOST_TASK_MAX_PER_CHAT", 3)
MAX_TASKS_GLOBAL = getattr(config, "HOST_TASK_MAX_GLOBAL", 10)
MAX_LOG_BYTES = getattr(config, "HOST_TASK_LOG_MAX_BYTES", 2097152)


class TaskAction(str, Enum):
    """Define available task actions."""

    WAIT = "wait"
    TAIL = "tail"
    KILL = "kill"
    LIST = "list"
    STATUS = "status"
    SEND_INPUT = "send_input"


class TaskStatus(str, Enum):
    """Define task lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    TIMEOUT = "timeout"


@dataclass
class TaskInfo:
    """Store task process information."""

    task_id: str
    chat_id: str
    pid: int
    pgid: int
    proc_start_time: int
    command: list[str]
    cwd: str
    created_at: float
    status: TaskStatus
    exit_code: int | None
    log_path: str


class TaskManager:
    """Manage isolated asynchronous task processes."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._buffers: dict[str, Deque[str]] = {}
        self._drainers: dict[str, asyncio.Task] = {}
        self._locks = asyncio.Lock()
        self._log_dir = DEFAULT_LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)

    async def spawn_process(self, command: list[str], cwd: str = ".", chat_id: str = "default") -> str:
        """Start an isolated process and register its task."""
        await self._check_quota(chat_id)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            start_new_session=True,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        task_id = uuid.uuid4().hex
        log_path = str(self._log_dir / f"{task_id}.log")
        task = TaskInfo(
            task_id=task_id,
            chat_id=chat_id,
            pid=process.pid,
            pgid=os.getpgid(process.pid),
            proc_start_time=get_proc_start_time(process.pid),
            command=command,
            cwd=cwd,
            created_at=time.time(),
            status=TaskStatus.RUNNING,
            exit_code=None,
            log_path=log_path,
        )
        async with self._locks:
            self._tasks[task_id] = task
            self._processes[task_id] = process
            self._buffers[task_id] = deque(maxlen=DEFAULT_RING_SIZE)
        self._drainers[task_id] = asyncio.create_task(self._drain_streams(task_id))
        return task_id

    async def _check_quota(self, chat_id: str) -> None:
        async with self._locks:
            active = [item for item in self._tasks.values() if item.status == TaskStatus.RUNNING]
            chat_active = [item for item in active if item.chat_id == chat_id]
            if len(active) >= MAX_TASKS_GLOBAL or len(chat_active) >= MAX_TASKS_PER_CHAT:
                raise RuntimeError("task quota exceeded")

    async def _drain_streams(self, task_id: str) -> None:
        process = self._processes[task_id]
        streams = [process.stdout, process.stderr]
        with open(self._tasks[task_id].log_path, "ab") as log_file:
            await asyncio.gather(*(self._drain_one(task_id, stream, log_file) for stream in streams))
        code = await process.wait()
        async with self._locks:
            task = self._tasks[task_id]
            task.exit_code = code
            task.status = TaskStatus.COMPLETED if code == 0 else TaskStatus.FAILED

    async def _drain_one(self, task_id: str, stream, log_file) -> None:
        while True:
            data = await stream.readline()
            if not data:
                break
            text = data.decode(errors="replace")
            self._buffers[task_id].append(text)
            log_file.write(data)
            log_file.flush()

    async def wait_task(self, task_id: str, timeout: float | None = None) -> dict:
        """Wait for task completion and return state."""
        if task_id not in self._tasks:
            raise KeyError(task_id)
        drain = self._drainers.get(task_id)
        if drain:
            if timeout is not None:
                await asyncio.wait_for(asyncio.shield(drain), timeout=timeout)
            else:
                await drain
        return await self.status_task(task_id)

    async def tail_task(self, task_id: str, lines: int = 50) -> str:
        """Return the last N lines of task output within a byte cap."""
        limit = getattr(config, "HOST_TASK_MAX_TAIL_BYTES", 65536)
        buffer = self._buffers.get(task_id)
        if buffer:
            output = "".join(list(buffer)[-lines:])
        else:
            with open(self._tasks[task_id].log_path, "rb") as file_handle:
                file_handle.seek(0, os.SEEK_END)
                position = file_handle.tell()
                file_handle.seek(max(0, position - limit), os.SEEK_SET)
                output = file_handle.read().decode(errors="replace")
            output = "\n".join(output.splitlines()[-lines:])
        encoded = output.encode("utf-8", errors="replace")
        if len(encoded) > limit:
            output = encoded[-limit:].decode("utf-8", errors="replace")
        return output

    async def kill_task(self, task_id: str) -> dict:
        """Terminate a task process group."""
        task = self._tasks[task_id]
        try:
            os.killpg(task.pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await asyncio.sleep(TERM_SIGNAL_GRACE)
        process = self._processes[task_id]
        if process.returncode is None:
            try:
                os.killpg(task.pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        task.status = TaskStatus.KILLED
        return await self.status_task(task_id)

    async def status_task(self, task_id: str) -> dict:
        """Return one task state."""
        return asdict(self._tasks[task_id])

    async def list_tasks(self, chat_id: str | None = None) -> list[dict]:
        """Return visible task states."""
        return [asdict(item) for item in self._tasks.values() if chat_id is None or item.chat_id == chat_id]

    async def send_input(self, task_id: str, data: str) -> dict:
        """Send input to a running task."""
        process = self._processes[task_id]
        process.stdin.write(data.encode())
        await process.stdin.drain()
        return {"status": "sent"}

    async def adaptive_execute(self, command: list[str], cwd: str = ".", chat_id: str = "default") -> dict:
        """Start a task and return its identifier."""
        task_id = await self.spawn_process(command, cwd, chat_id)
        return {"task_id": task_id}


def get_proc_start_time(pid: int) -> int:
    """Read process start time from proc stat."""
    stat = Path(f"/proc/{pid}/stat").read_text()
    after_comm = stat[stat.rfind(")") + 2 :]
    fields = after_comm.split()
    return int(fields[STAT_START_FIELD - 3])


def read_tail(path: str, byte_limit: int) -> str:
    """Read log tail within a byte limit."""
    with open(path, "rb") as file_handle:
        file_handle.seek(0, os.SEEK_END)
        position = file_handle.tell()
        file_handle.seek(max(0, position - byte_limit), os.SEEK_SET)
        return file_handle.read().decode(errors="replace")


_TASK_MANAGER = TaskManager()


def get_task_manager() -> TaskManager:
    """Return the shared task manager instance."""
    return _TASK_MANAGER


class _TaskEventLoop:
    """Provide a dedicated background event loop for process tasks."""

    def __init__(self) -> None:
        import concurrent.futures
        import threading

        self._futures = concurrent.futures
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="bqa-task-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout: float | None = None):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout=timeout)
        except self._futures.TimeoutError as exc:
            raise TimeoutError("Task operation timed out.") from exc


_BG_LOOP: _TaskEventLoop | None = None


def get_task_event_loop() -> _TaskEventLoop:
    """Return the shared background event loop for tasks."""
    global _BG_LOOP
    if _BG_LOOP is None:
        _BG_LOOP = _TaskEventLoop()
    return _BG_LOOP


def run_task_coro(coro, timeout: float | None = None):
    """Execute a task coroutine on the dedicated task event loop."""
    return get_task_event_loop().run(coro, timeout=timeout)


async def bridge_task_coro(coro, timeout: float | None = None):
    """Bridge a coroutine to run on the dedicated background task loop from any caller loop."""
    bg_loop = get_task_event_loop().loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is bg_loop:
        return await coro

    fut = asyncio.run_coroutine_threadsafe(coro, bg_loop)
    if current_loop is not None:
        wrapped = asyncio.wrap_future(fut)
        if timeout is not None:
            return await asyncio.wait_for(wrapped, timeout=timeout)
        return await wrapped
    return fut.result(timeout=timeout)
