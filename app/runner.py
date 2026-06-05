import uuid
import json
import time
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from app.config import RUNS_DIR, MAX_OUTPUT_BYTES
from app.schemas import FallbackRequest, FallbackResponse
from app.file_package import check_total_size_and_validate, write_files, sha256_bytes
from app.docker_runner import run_in_docker
from app.transcript import generate_transcript
from app.logging_audit import log_audit_event

def create_run_id() -> str:
    """Generates a unique runner ID based on timestamp and randomness."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rand = uuid.uuid4().hex[:8]
    return f"run_{timestamp}_{rand}"

def execute_fallback_solver(req: FallbackRequest, derived_from: Optional[str] = None) -> FallbackResponse:
    """Orchestrates the entire solver execution cycle."""
    run_id = create_run_id()
    created_at = datetime.now(timezone.utc).isoformat()
    
    # 1. Setup directories
    run_dir = RUNS_DIR / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    log_audit_event("RUN_REQUEST", {
        "run_id": run_id,
        "target": f"{req.target.host}:{req.target.port}",
        "language": req.language,
        "entrypoint": req.entrypoint,
        "timeout_seconds": req.timeout_seconds
    })
    
    # 2. Parse and decode package payloads
    decoded_files = check_total_size_and_validate(req.files)
    
    # Ensure entrypoint actually exists in the package
    entrypoint_found = False
    for path, _ in decoded_files:
        if path == req.entrypoint:
            entrypoint_found = True
            break
            
    if not entrypoint_found:
        raise ValueError(f"Entrypoint file '{req.entrypoint}' is missing from the package files.")
        
    # Write package files to target input dir
    write_files(input_dir, decoded_files)
    
    # Compute metadata lists
    files_info = []
    for rel_path, content_bytes in decoded_files:
        files_info.append({
            "path": rel_path,
            "size": len(content_bytes),
            "sha256": sha256_bytes(content_bytes)
        })
        
    log_audit_event("FILES_WRITTEN", {
        "run_id": run_id,
        "count": len(decoded_files),
        "total_bytes": sum(f["size"] for f in files_info)
    })
    
    # 3. Trigger Docker isolation runner
    container_name = f"fallback_{run_id}"
    target_str = f"{req.target.host}:{req.target.port}"
    
    start_time = time.time()
    exit_code, stdout, stderr, timed_out = run_in_docker(
        container_name=container_name,
        run_input_dir=input_dir,
        entrypoint=req.entrypoint,
        args=req.args,
        env=req.env,
        timeout=req.timeout_seconds,
        language=req.language,
        target_host=req.target.host,
        target_port=req.target.port
    )
    duration_ms = int((time.time() - start_time) * 1000)
    
    # 4. Truncate outputs if they exceed configured MAX_OUTPUT_BYTES
    truncated = False
    if len(stdout) > MAX_OUTPUT_BYTES:
        stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [STDOUT TRUNCATED BY MCP SERVER] ..."
        truncated = True
        
    if len(stderr) > MAX_OUTPUT_BYTES:
        stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [STDERR TRUNCATED BY MCP SERVER] ..."
        truncated = True
        
    # Persist raw run logs
    (output_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (output_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    
    stdout_sha256 = sha256_bytes(stdout.encode('utf-8'))
    stderr_sha256 = sha256_bytes(stderr.encode('utf-8'))
    
    # 5. Construct execution Command representation for transcript
    exec_executable = "sage" if req.language.lower() == "sage" else "python3"
    run_cmd = f"{exec_executable} {req.entrypoint}"
    if req.args:
        run_cmd += " " + " ".join(req.args)
        
    # Generate the formatted audit transcript
    transcript_content, transcript_sha256 = generate_transcript(
        run_id=run_id,
        target=target_str,
        sandbox_failure=req.sandbox_failure.model_dump(),
        local_validation=req.local_validation.model_dump(),
        files_info=files_info,
        command=run_cmd,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms
    )
    
    (output_dir / "transcript.txt").write_text(transcript_content, encoding="utf-8")
    
    # 6. Save metadata
    metadata = {
        "run_id": run_id,
        "derived_from": derived_from,
        "created_at": created_at,
        "target": target_str,
        "language": req.language,
        "entrypoint": req.entrypoint,
        "timeout_seconds": req.timeout_seconds,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "sandbox_failure": req.sandbox_failure.model_dump(),
        "local_validation": req.local_validation.model_dump(),
        "files": files_info,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "transcript_sha256": transcript_sha256
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    
    log_summary = [
        f"RUN_START target={target_str}",
        f"FILES_WRITTEN count={len(decoded_files)} total_bytes={sum(f['size'] for f in files_info)}",
        f"DOCKER_START image={req.language}-runner",
        f"RUN_END exit_code={exit_code} duration_ms={duration_ms}"
    ]
    
    log_audit_event("RUN_COMPLETE", {
        "run_id": run_id,
        "target": target_str,
        "exit_code": exit_code,
        "duration_ms": duration_ms
    })
    
    return FallbackResponse(
        ok=True,
        run_id=run_id,
        target=target_str,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        stdout_sha256=stdout_sha256,
        stderr_sha256=stderr_sha256,
        transcript_sha256=transcript_sha256,
        truncated=truncated,
        log_summary=log_summary
    )
