import asyncio
from typing import Any

from app.mcp_server import mcp
from app.task_manager import bridge_task_coro, get_task_manager
from app.tools_common import (
    _guard_chat_id,
    enforce_bridge_payload_limit,
    enforce_payload,
)


@mcp.tool()
async def task(
    action: str,
    chat_id: str,
    task_id: str | None = None,
    lines: int = 50,
    timeout_ms: int = 30000,
    stdin_data: str | None = None,
) -> Any:
    """Manage tasks.
    Use wait for task completion.
    Do not call status in a loop. Use wait for completion.
    Return task information or output.
    """
    validated, rejection = _guard_chat_id("task", chat_id)
    if rejection is not None:
        return enforce_bridge_payload_limit(rejection, "task")

    manager = get_task_manager()
    actions = {
        "wait": manager.wait_task,
        "tail": manager.tail_task,
        "kill": manager.kill_task,
        "list": manager.list_tasks,
        "status": manager.status_task,
        "send_input": manager.send_input,
    }
    if action not in actions:
        raise ValueError(f"Unsupported task action: {action}")

    handler = actions[action]
    if action == "list":
        coro = handler(chat_id=chat_id)
    elif action == "tail":
        coro = handler(task_id=task_id, lines=lines)
    elif action == "wait":
        coro = handler(task_id=task_id, timeout=timeout_ms / 1000)
    elif action == "send_input":
        coro = handler(task_id=task_id, data=stdin_data or "")
    else:
        coro = handler(task_id=task_id)

    try:
        result = await bridge_task_coro(coro)
    except (TimeoutError, asyncio.TimeoutError):
        if action == "wait" and task_id:
            current_status = await bridge_task_coro(manager.status_task(task_id=task_id))
            result = {
                "ok": True,
                "timed_out": True,
                "task_id": task_id,
                "status": current_status.get("status"),
                "message": (
                    f"Task did not complete within {timeout_ms}ms. Still running in background. "
                    "Use task(action='wait') to continue waiting or task(action='tail') to inspect output."
                ),
            }
        else:
            raise

    return enforce_payload(result)

