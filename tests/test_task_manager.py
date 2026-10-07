import asyncio
import os
import signal

from app.task_manager import TaskManager, get_proc_start_time, read_tail


def test_process_group_isolation():
    async def run():
        manager = TaskManager()
        task_id = await manager.spawn_process(["python", "-c", "import time; time.sleep(1)"])
        info = await manager.status_task(task_id)
        assert info["pgid"] == info["pid"]
        assert info["proc_start_time"] == get_proc_start_time(info["pid"])
        await manager.kill_task(task_id)

    asyncio.run(run())


def test_stream_draining_without_deadlock():
    async def run():
        manager = TaskManager()
        code = "import sys; [print('x'*1000) for _ in range(2000)]"
        task_id = await manager.spawn_process(["python", "-c", code])
        result = await manager.wait_task(task_id)
        assert result["exit_code"] == 0

    asyncio.run(run())


def test_backward_tail_limit(tmp_path):
    path = tmp_path / "log"
    path.write_bytes(b"0123456789")
    assert read_tail(str(path), 4) == "6789"


def test_kill_signal_escalation():
    async def run():
        manager = TaskManager()
        task_id = await manager.spawn_process(["python", "-c", "import time; time.sleep(10)"])
        result = await manager.kill_task(task_id)
        assert result["status"] == "killed"

    asyncio.run(run())


def test_pid_start_time_verification():
    async def run():
        manager = TaskManager()
        task_id = await manager.spawn_process(["python", "-c", "import time; time.sleep(1)"])
        info = await manager.status_task(task_id)
        assert info["proc_start_time"] > 0
        await manager.kill_task(task_id)

    asyncio.run(run())
