from typing import Any, Dict, List

from app.logging_audit import log_audit_event
from app.mcp_server import mcp
from app.security import format_error_response
from app.tools.basic_runner import run_basic_python_solver
from app.tools.health import get_capabilities, health_check


@mcp.tool(
    name="run_safe_smoke_test",
    description=(
        "Run a harmless MCP self-test for ChatGPT connectivity. "
        "Checks health, capabilities, and a print-only basic Python solver without network access."
    ),
)
def run_safe_smoke_test(label: str = "safe_smoke_test") -> Dict[str, Any]:
    """Runs low-risk checks without Docker, workspace mutation, or network targets."""
    try:
        tests: List[Dict[str, Any]] = []

        health = health_check()
        tests.append({
            "name": "health_check",
            "ok": bool(health.get("ok")),
            "details": {
                "service": health.get("service"),
                "version": health.get("version"),
                "tool_profile": health.get("tool_profile"),
            },
        })

        capabilities = get_capabilities()
        tests.append({
            "name": "get_capabilities",
            "ok": bool(capabilities.get("ok")),
            "details": {
                "core_tools": capabilities.get("core_tools", []),
                "advanced_tools_enabled": capabilities.get("advanced_tools_enabled"),
            },
        })

        solver = run_basic_python_solver(
            files=[{
                "name": "solve.py",
                "content": "print('MCP_SAFE_SMOKE_TEST_OK')\n",
            }],
            entrypoint="solve.py",
            timeout_seconds=5,
        )
        tests.append({
            "name": "run_basic_python_solver",
            "ok": bool(solver.get("ok")) and solver.get("exit_code") == 0 and "MCP_SAFE_SMOKE_TEST_OK" in solver.get("stdout", ""),
            "details": {
                "run_id": solver.get("run_id"),
                "exit_code": solver.get("exit_code"),
                "stdout_sha256": solver.get("stdout_sha256"),
            },
        })

        ok = all(test["ok"] for test in tests)
        log_audit_event("SAFE_SMOKE_TEST", {"label": label, "ok": ok})
        return {
            "ok": ok,
            "label": label,
            "tests": tests,
        }
    except Exception as e:
        log_audit_event("SAFE_SMOKE_TEST_FAIL", {"label": label, "error": str(e)})
        return format_error_response(e)
