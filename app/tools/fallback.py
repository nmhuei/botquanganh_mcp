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


@mcp.tool(
    name="upload_artifact",
    description="Upload a solver source file or utility payload to the server's artifact cache. Returns an artifact_id for file entry references."
)
def upload_artifact(
    filename: str,
    content: str,
    encoding: str = "text"
) -> Dict[str, Any]:
    """Uploads a file payload, computes its SHA-256, and stores it in the persistent artifacts directory."""
    try:
        from app.config import ARTIFACTS_DIR
        import hashlib
        import base64
        
        # Validate filename
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError(f"Invalid filename: '{filename}'")
            
        if encoding not in ("text", "base64"):
            raise ValueError("encoding must be 'text' or 'base64'")
            
        # Decode and validate content bytes
        if encoding == "base64":
            try:
                content_bytes = base64.b64decode(content)
            except Exception as e:
                raise ValueError(f"Invalid base64 payload: {str(e)}")
        else:
            content_bytes = content.encode("utf-8")
            
        # Calculate SHA-256 to form artifact ID
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = f"art_{sha256}"
        
        # Save to artifacts directory
        artifact_path = ARTIFACTS_DIR / artifact_id
        artifact_path.write_bytes(content_bytes)
        
        log_audit_event("UPLOAD_ARTIFACT", {
            "filename": filename,
            "artifact_id": artifact_id,
            "size": len(content_bytes)
        })
        
        return {
            "ok": True,
            "artifact_id": artifact_id,
            "sha256": sha256,
            "size": len(content_bytes),
            "filename": filename
        }
    except Exception as e:
        log_audit_event("UPLOAD_ARTIFACT_FAIL", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="rerun_run",
    description="Run a new fallback solver by inheriting and patching workspace or execution config of an existing run."
)
def rerun_run(
    run_id: str,
    patch: Dict[str, Any]
) -> Dict[str, Any]:
    """Patches an existing solver run workspace and execution config to trigger a new fallback run."""
    try:
        from app.config import RUNS_DIR
        from app.tools.runs import validate_run_id_safe
        import json
        import base64
        
        # 1. Validate original run ID format
        validate_run_id_safe(run_id)
        
        # 2. Retrieve old metadata
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory for run_id '{run_id}' not found.")
            
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata for run_id '{run_id}' is missing.")
            
        old_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        
        # 3. Reconstruct files from original workspace
        files_info = old_meta.get("files", [])
        reconstructed_files = []
        run_input_dir = run_dir / "input"
        
        for f_info in files_info:
            path_str = f_info["path"]
            file_path = run_input_dir / path_str
            if file_path.exists():
                content_bytes = file_path.read_bytes()
                # Encode as base64 to preserve binary safety
                content_b64 = base64.b64encode(content_bytes).decode('utf-8')
                reconstructed_files.append({
                    "path": path_str,
                    "encoding": "base64",
                    "content": content_b64
                })
                
        # 4. Apply workspace files patch
        workspace_patch = patch.get("workspace", {})
        patched_files_map = {f["path"]: f for f in reconstructed_files}
        
        for patch_file in workspace_patch.get("files", []):
            patched_files_map[patch_file["path"]] = patch_file
            
        final_files = list(patched_files_map.values())
        
        # 5. Extract original target and details
        target_str = old_meta.get("target")
        if ":" not in target_str:
            raise ValueError(f"Corrupt target format in run metadata: '{target_str}'")
        host, port_str = target_str.split(":", 1)
        target_dict = {
            "host": host,
            "port": int(port_str),
            "protocol": "tcp"
        }
        
        # 6. Extract sandbox failure and local validation
        sandbox_failure_dict = old_meta.get("sandbox_failure")
        local_validation_dict = old_meta.get("local_validation")
        
        # 7. Merge execution config and properties
        final_language = workspace_patch.get("language", old_meta.get("language", "python"))
        final_entrypoint = workspace_patch.get("entrypoint", old_meta.get("entrypoint", "solve.py"))
        
        execution_patch = patch.get("execution", {})
        final_args = execution_patch.get("args", old_meta.get("args", []))
        final_env = execution_patch.get("env", old_meta.get("env", {}))
        final_timeout = execution_patch.get("timeout_seconds", old_meta.get("timeout_seconds", 30))
        
        # 8. Re-validate request and execute
        req = FallbackRequest(
            target=target_dict,
            language=final_language,
            entrypoint=final_entrypoint,
            args=final_args,
            env=final_env,
            timeout_seconds=final_timeout,
            sandbox_failure=sandbox_failure_dict,
            local_validation=local_validation_dict,
            files=final_files
        )
        
        # Security checks
        validate_target_allowlisted(req.target.host, req.target.port)
        block_private_or_local_host(req.target.host, req.target.port)
        validate_timeout(req.timeout_seconds)
        validate_language(req.language)
        validate_args(req.args)
        
        # Execute the solver
        res = execute_fallback_solver(req, derived_from=run_id)
        
        # Return response including derived_from attribute
        response_dict = res.model_dump()
        response_dict["derived_from"] = run_id
        return response_dict
        
    except Exception as e:
        log_audit_event("RERUN_ERROR", {
            "error": str(e),
            "original_run_id": run_id
        })
        return format_error_response(e)
