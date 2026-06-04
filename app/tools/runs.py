import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict
from app.mcp_server import mcp
from app.config import RUNS_DIR
from app.logging_audit import get_audit_logs_for_run, log_audit_event

RUN_ID_PATTERN = re.compile(r"^run_[0-9]{8}_[0-9]{6}_[a-f0-9]+$")

def validate_run_id_safe(run_id: str) -> None:
    """Ensures the run_id format is valid, preventing path traversal via ID parameters."""
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError("Invalid run_id format.")

@mcp.tool(
    name="get_run_log",
    description="Retrieve execution metadata, container stdout/stderr, audit events, and transcript for a run."
)
def get_run_log(run_id: str, include_transcript: bool = True) -> Dict[str, Any]:
    """Fetches full log trace and file package metadata for a specific run ID."""
    try:
        validate_run_id_safe(run_id)
        
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory for run_id '{run_id}' does not exist.")
            
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file for run_id '{run_id}' is missing.")
            
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        audit_log = get_audit_logs_for_run(run_id)
        
        transcript = ""
        if include_transcript:
            transcript_path = run_dir / "output" / "transcript.txt"
            if transcript_path.exists():
                transcript = transcript_path.read_text(encoding="utf-8")
                
        return {
            "ok": True,
            "run_id": run_id,
            "metadata": {
                "target": metadata.get("target"),
                "exit_code": metadata.get("exit_code"),
                "duration_ms": metadata.get("duration_ms"),
                "created_at": metadata.get("created_at")
            },
            "audit_log": audit_log,
            "transcript": transcript,
            "sha256": {
                "stdout": metadata.get("stdout_sha256", ""),
                "stderr": metadata.get("stderr_sha256", ""),
                "transcript": metadata.get("transcript_sha256", "")
            }
        }
    except Exception as e:
        log_audit_event("GET_RUN_LOG_FAIL", {"error": str(e), "run_id": run_id})
        raise e

@mcp.tool(
    name="list_recent_runs",
    description="List history summaries of previous solver executions."
)
def list_recent_runs(limit: int = 20) -> Dict[str, Any]:
    """Retrieves summaries of the most recent solver runs, sorted newest first."""
    try:
        
        runs = []
        if RUNS_DIR.exists():
            for p in RUNS_DIR.iterdir():
                if p.is_dir() and p.name.startswith("run_"):
                    meta_path = p / "metadata.json"
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            runs.append({
                                "run_id": meta.get("run_id"),
                                "target": meta.get("target"),
                                "exit_code": meta.get("exit_code"),
                                "created_at": meta.get("created_at"),
                                "duration_ms": meta.get("duration_ms")
                            })
                        except Exception:
                            # Corrupt metadata file, skip it
                            continue
                            
        # Sort newest runs first
        runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {
            "ok": True,
            "runs": runs[:limit]
        }
    except Exception as e:
        log_audit_event("LIST_RUNS_FAIL", {"error": str(e)})
        raise e

@mcp.tool(
    name="delete_run",
    description="Permanently delete a run's inputs, outputs, transcripts and metadata."
)
def delete_run(run_id: str) -> Dict[str, Any]:
    """Removes a run directory from storage."""
    try:
        validate_run_id_safe(run_id)
        
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run folder for run_id '{run_id}' not found.")
            
        shutil.rmtree(run_dir)
        log_audit_event("RUN_DELETED", {"run_id": run_id})
        
        return {
            "ok": True,
            "message": f"Run '{run_id}' deleted successfully."
        }
    except Exception as e:
        log_audit_event("DELETE_RUN_FAIL", {"error": str(e), "run_id": run_id})
        raise e
