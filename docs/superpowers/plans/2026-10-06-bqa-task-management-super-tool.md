# BQA MCP 2.0 Task Management Super-Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade, asynchronous Task Management Subsystem (`TaskManager`) and MCP Super-Tool (`task`) for BQA MCP 2.0, providing hybrid adaptive command execution, full Linux process group isolation (`setsid`), deadlock-free stream draining, anti-polling synchronization (`wait`), and strict 512,000-byte wire payload defense.

**Architecture:** A singleton `TaskManager` manages process lifecycles with `asyncio.create_subprocess_exec(start_new_session=True)`. Output streams are drained concurrently to in-memory ring buffers and disk logs. The `terminal_execute` tool provides hybrid adaptive detach (synchronous wait up to 5s, auto-detach if longer). The `task` tool exposes `wait`, `tail`, `kill`, `list`, and `status` actions with ASD-STE100 anti-polling docstrings.

**Tech Stack:** Python >=3.10, FastMCP 3.4.7, Linux `/proc/<pid>/stat`, `asyncio`, `pytest`.

**Spec:** Synthesized from 5-track deep research with `gpt-5-6-thinking` (`sess_4ef6d661`, `sess_6ade1388`, `sess_2c8f592e`, `sess_f2f92752`, `sess_3541c2c7`, `sess_45136e16`, `sess_294af97d`).

## Global Constraints

- Never touch, restart, or kill the running Cloudflare tunnel process (PID 7707).
- Zero-hardcoding invariant: All quotas, timeouts, and limits must load from `app.config` backed by `.env`.
- Maximum response payload: strictly `<= 512,000` bytes across all MCP tool returns.
- Documentation & docstrings: Strictly conform to ASD-STE100 (< 25 words/sentence, imperative verbs).
- Linux Systems Integrity: Mandatory `start_new_session=True`, process group signal escalation (`os.killpg`), `/proc/<pid>/stat` starttime verification against PID recycling.
- Anti-Duplication (DRY): Share primitives via `app/tools_common.py`. No copy-pasting logic.
- Sandbox: All scratch scripts, temp test artifacts must reside in `~/Downloads/bqa-trash/`.

---

### Task 1: Configuration & Common Primitives

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `app/tools_common.py`
- Test: `tests/test_task_config.py`

**Interfaces:**
- Consumes: `.env` environment variables.
- Produces:
  - `app.config.HOST_TASK_MAX_PER_CHAT: int` (default 3)
  - `app.config.HOST_TASK_MAX_GLOBAL: int` (default 10)
  - `app.config.HOST_TASK_WAIT_BEFORE_ASYNC_MS: int` (default 5000)
  - `app.config.HOST_TASK_MAX_TAIL_BYTES: int` (default 65536)
  - `app.config.HOST_TASK_LOG_MAX_BYTES: int` (default 2097152)
  - `app.config.HOST_TASK_KILL_GRACE_SECONDS: int` (default 3)
  - `app.tools_common.enforce_payload(data: Any, max_bytes: int = 500000) -> Any`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_task_config.py
import pytest
from app import config
from app.tools_common import enforce_payload

def test_task_config_defaults():
    assert config.HOST_TASK_MAX_PER_CHAT >= 1
    assert config.HOST_TASK_MAX_GLOBAL >= config.HOST_TASK_MAX_PER_CHAT
    assert config.HOST_TASK_WAIT_BEFORE_ASYNC_MS >= 1000
    assert config.HOST_TASK_MAX_TAIL_BYTES <= 128 * 1024
    assert config.HOST_TASK_LOG_MAX_BYTES >= 1024 * 1024
    assert config.HOST_TASK_KILL_GRACE_SECONDS >= 1

def test_enforce_payload_within_limit():
    data = {"status": "ok", "message": "hello"}
    assert enforce_payload(data) == data

def test_enforce_payload_exceeding_limit():
    huge_data = {"data": "x" * 600000}
    with pytest.raises(ValueError, match="exceeds wire limit"):
        enforce_payload(huge_data, max_bytes=500000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_task_config.py -v`
Expected: FAIL with AttributeError (missing HOST_TASK_* variables in config).

- [ ] **Step 3: Implement configuration and tools_common helpers**

Add task settings to `app/config.py` and `.env.example`.
Update `app/tools_common.py` with `enforce_payload` and shared envelope helpers.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_task_config.py -v`
Expected: PASS.

---

### Task 2: TaskManager Core Subsystem (`app/task_manager.py`)

**Files:**
- Create: `app/task_manager.py`
- Test: `tests/test_task_manager.py`

**Interfaces:**
- Consumes: `app.config`, `app.tools_common`.
- Produces:
  - `TaskAction(str, Enum)`: `WAIT = "wait"`, `TAIL = "tail"`, `KILL = "kill"`, `LIST = "list"`, `STATUS = "status"`, `SEND_INPUT = "send_input"`
  - `TaskStatus(str, Enum)`: `QUEUED = "queued"`, `RUNNING = "running"`, `COMPLETED = "completed"`, `FAILED = "failed"`, `KILLED = "killed"`, `TIMEOUT = "timeout"`
  - `TaskInfo` dataclass: `task_id`, `chat_id`, `pid`, `pgid`, `proc_start_time`, `command`, `cwd`, `created_at`, `status`, `exit_code`, `log_path`
  - `TaskManager` class:
    - `async def spawn_process(...) -> str`
    - `async def adaptive_execute(...) -> dict`
    - `async def wait_task(...) -> dict`
    - `async def tail_task(...) -> str`
    - `async def kill_task(...) -> dict`
    - `async def list_tasks(...) -> list[dict]`
    - `async def send_input(...) -> dict`

- [ ] **Step 1: Write the failing unit tests**

Write `tests/test_task_manager.py` covering:
- Process spawning with `start_new_session=True` (PGID isolation).
- Deadlock-free async stdout/stderr stream draining.
- Backward seeking tail reader with byte ceiling.
- Signal escalation (`SIGTERM` -> 3s -> `SIGKILL`).
- `/proc/<pid>/stat` starttime verification.
- Quota rejection when active tasks exceed limit.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_task_manager.py -v`
Expected: FAIL (module `app.task_manager` does not exist).

- [ ] **Step 3: Write `app/task_manager.py`**

Implement `TaskManager` using:
- `collections.deque(maxlen=1000)` in-memory ring buffer.
- Streaming to task log file in chat workspace or trash dir.
- Backward binary seek reader (`SEEK_END`) for tailing without reading entire file into RAM.
- `asyncio.Lock` guarding `self._tasks` state mutations.
- `get_proc_start_time(pid)` reading `/proc/<pid>/stat` field 22.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_task_manager.py -v`
Expected: PASS.

---

### Task 3: Super-Tool `task` and Hybrid Adaptive `terminal_execute`

**Files:**
- Create: `app/tools/task.py`
- Modify: `app/tools/terminal_execute.py`
- Modify: `app/mcp_server.py`
- Modify: `app/tools/server_info.py`
- Test: `tests/test_task_tool.py`

**Interfaces:**
- Consumes: `app.task_manager.TaskManager`, `app.tools_common`.
- Produces:
  - MCP Tool `task(action: str, chat_id: str, task_id: str | None = None, lines: int = 50, timeout_ms: int = 30000, stdin_data: str | None = None)`
  - MCP Tool `terminal_execute(command: str | list[str], cwd: str = ".", chat_id: str = "default", wait_ms_before_async: int = 5000, background: bool | None = None)`

- [ ] **Step 1: Write failing tool contract tests**

Write `tests/test_task_tool.py` testing:
- ASD-STE100 docstring length (< 25 words per sentence).
- Anti-polling guidance present in docstrings.
- Adaptive execution: short command returns inline, long command auto-detaches.
- Calling `task(action='wait')` blocks until completion.
- Calling `task(action='tail')` returns bounded lines.
- Calling `task(action='kill')` terminates process group.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_task_tool.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement tool functions & MCP registration**

- Implement `app/tools/task.py`.
- Refactor `app/tools/terminal_execute.py` to route through `TaskManager.adaptive_execute()`.
- Register `task` tool in `app/mcp_server.py`.
- Update `app/tools/server_info.py` catalog.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_task_tool.py -v`
Expected: PASS.

---

### Task 4: Dual-Audit, Adversarial Stress Testing & Regression Verification

**Files:**
- Audit Target: `app/task_manager.py`, `app/tools/task.py`, `app/tools/terminal_execute.py`
- Test: `tests/test_task_stress.py`

- [ ] **Step 1: Write Stress & Adversarial Test**
  - Test massive output generation (> 100,000 lines, > 10MB) to ensure zero pipe deadlock.
  - Test runaway infinite while-loop process terminated via `task(action='kill')`.
  - Test rapid parallel task execution under quota limits.

- [ ] **Step 2: Dispatch Dual-Audit with GPT-CLI Subagents**
  - Dispatch Auditor 1 (Red-Team): Scan for race conditions, signal safety, kernel deadlocks.
  - Dispatch Auditor 2 (Rules & Hygiene): Scan for hardcoding, DRY violations, shadow built-ins, ASD-STE100.
  - Fix any identified P0, P1, or P2 findings.

- [ ] **Step 3: Run Full Pytest Regression Suite**
  - Run `.venv/bin/python -m pytest tests/` to confirm 100% green without breaking existing workspace tools.
