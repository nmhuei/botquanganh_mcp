from typing import Any, Dict, List, Optional
from app.mcp_server import mcp
from app.schemas import FallbackRequest
from app.security import (
    validate_target_allowlisted,
    block_private_or_local_host,
    validate_timeout,
    validate_language,
    validate_args,
    format_error_response,
)
from app.runner import execute_fallback_solver
from app.logging_audit import log_audit_event

@mcp.tool(
    name="run_solver_fallback",
    description=(
        "Run a provided CTF/lab solver only as a fallback when the assistant has already solved locally "
        "and failed to connect to the remote target from its sandbox. "
        "Supported language environments:\n"
        "- 'python' (default) or 'pwn': Python 3.12 with pre-installed libraries: pwntools, pycryptodome (import Crypto), z3-solver (import z3), libnum, sympy, gmpy2, requests, tqdm, pyasn1, pyasn1-modules, playwright, cloakbrowser (requires args=['--no-sandbox']).\n"
        "- 'sage': SageMath with pre-installed libraries: native SageMath, pycryptodome, z3-solver, libnum, sympy, gmpy2, tqdm, pyasn1, pyasn1-modules.\n"
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
    """Runs a CTF solver package inside an isolated Docker container, returning execution outputs.

    Supported language environments (parameter 'language'):
    - 'python' (default) / 'pwn': Runs in Python 3.12-slim container.
      Pre-installed libraries (importable directly):
      * pwntools (import pwn)
      * pycryptodome (import Crypto)
      * z3-solver (import z3)
      * libnum (import libnum)
      * sympy (import sympy)
      * gmpy2 (import gmpy2)
      * requests (import requests)
      * tqdm (import tqdm)
      * pyasn1 (import pyasn1)
      * pyasn1-modules (import pyasn1_modules)
      * playwright (import playwright)
      * cloakbrowser (import cloakbrowser). Note: When running playwright or cloakbrowser, you MUST pass "--no-sandbox" in the args parameter.

    - 'sage': Runs in SageMath container.
      Pre-installed libraries (importable directly):
      * SageMath (native)
      * pycryptodome (import Crypto)
      * z3-solver (import z3)
      * libnum (import libnum)
      * sympy (import sympy)
      * gmpy2 (import gmpy2)
      * tqdm (import tqdm)
      * pyasn1 (import pyasn1)
      * pyasn1-modules (import pyasn1_modules)

    This tool is only for fallback runs and requires sandbox_failure reason, local_validation, and allowlisted target.
    """
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
        return format_error_response(e)


@mcp.tool(
    name="validate_run_request",
    description="Dry-run validation for run_solver_fallback. Checks parameters, targets, policy, timeout, and schema without executing the solver container."
)
def validate_run_request(
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
    """Dry-run validation of a solver fallback request."""
    try:
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
        validate_target_allowlisted(req.target.host, req.target.port)
        block_private_or_local_host(req.target.host, req.target.port)
        validate_timeout(req.timeout_seconds)
        validate_language(req.language)
        validate_args(req.args)
        
        # Verify entrypoint file is specified in files list
        entrypoint_found = False
        for f in req.files:
            if f.path == req.entrypoint:
                entrypoint_found = True
                break
        if not entrypoint_found:
            raise ValueError(f"Entrypoint file '{req.entrypoint}' is missing from the files list.")

        return {
            "ok": True,
            "valid": True,
            "normalized": {
                "language": req.language,
                "timeout_seconds": req.timeout_seconds
            },
            "warnings": []
        }
    except Exception as e:
        err = format_error_response(e)
        return {
            "ok": False,
            "valid": False,
            "error": err["error"]
        }
