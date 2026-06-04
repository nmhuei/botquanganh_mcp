from typing import Any, Dict, List, Optional
from app.mcp_server import mcp
from app.schemas import FallbackRequest
from app.security import (
    validate_target_allowlisted,
    block_private_or_local_host,
    validate_timeout,
    validate_language,
    validate_args,
)
from app.runner import execute_fallback_solver
from app.logging_audit import log_audit_event

@mcp.tool(
    name="run_solver_fallback",
    description=(
        "Run a provided CTF/lab solver only as a fallback when the assistant has already solved locally "
        "and failed to connect to the remote target from its sandbox. "
        "Do not use this tool for normal local solving. "
        "Do not use this tool if the assistant sandbox can reach the remote server. "
        "The server must reject requests without sandbox_failure evidence, local_validation summary, "
        "and an allowlisted target. "
        "The solver runs inside an isolated Docker container and returns stdout, stderr, hashes, and transcript logs."
    )
)
def run_solver_fallback(
    target: Dict[str, Any],
    sandbox_failure: Dict[str, Any],
    local_validation: Dict[str, Any],
    files: List[Dict[str, Any]],
    language: str = "python",
    entrypoint: str = "solve.py",
    args: List[str] = [],
    env: Dict[str, str] = {},
    timeout_seconds: int = 30
) -> Dict[str, Any]:
    """Runs a CTF solver package inside an isolated Docker container, returning execution outputs."""
    try:
        # 1. Parse and Validate request schema
        req = FallbackRequest(
            target=target,
            language=language,
            entrypoint=entrypoint,
            args=args,
            env=env,
            timeout_seconds=timeout_seconds,
            sandbox_failure=sandbox_failure,
            local_validation=local_validation,
            files=files
        )

        
        # 3. Security checks
        validate_target_allowlisted(req.target.host, req.target.port)
        block_private_or_local_host(req.target.host, req.target.port)
        validate_timeout(req.timeout_seconds)
        validate_language(req.language)
        validate_args(req.args)
        
        # 4. Execution
        res = execute_fallback_solver(req)
        return res.model_dump()
        
    except Exception as e:
        # Extract host information if possible
        host_info = None
        if isinstance(target, dict):
            host_info = target.get("host")
            
        log_audit_event("RUN_ERROR", {
            "error": str(e),
            "target_host": host_info
        })
        raise e
