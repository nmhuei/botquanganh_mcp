import uuid
import re
import json
import base64
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
from app.mcp_server import mcp
from app.config import WORKSPACES_DIR, MAX_SINGLE_FILE_BYTES
from app.logging_audit import log_audit_event
from app.security import format_error_response
from app.file_package import sha256_bytes

WORKSPACE_ID_PATTERN = re.compile(r"^ws_[0-9]{8}_[0-9]{6}_[a-f0-9]+$")

def validate_workspace_id_safe(workspace_id: str) -> None:
    """Ensures the workspace_id format is valid, preventing path traversal."""
    if not WORKSPACE_ID_PATTERN.match(workspace_id):
        raise ValueError("Invalid workspace_id format.")

def create_workspace_id() -> str:
    """Generates a unique workspace ID based on timezone-aware UTC time and randomness."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"ws_{timestamp}_{uuid.uuid4().hex[:8]}"


@mcp.tool(
    name="create_workspace",
    description="Create a persistent workspace to upload files and run multiple commands across steps."
)
def create_workspace(label: str = "") -> Dict[str, Any]:
    """Creates a new workspace directory and initializes metadata.json."""
    try:
        workspace_id = create_workspace_id()
        workspace_dir = WORKSPACES_DIR / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "workspace_id": workspace_id,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": []
        }
        (workspace_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        log_audit_event("WORKSPACE_CREATED", {"workspace_id": workspace_id, "label": label})
        return {"ok": True, "workspace_id": workspace_id, "label": label}

    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="upload_file_to_workspace",
    description="Upload a challenge file (binary, pcap, image, etc.) into a workspace."
)
def upload_file_to_workspace(
    workspace_id: str,
    filename: str,
    content: str,
    encoding: str = "base64"
) -> Dict[str, Any]:
    """Uploads a file payload into a specified workspace."""
    try:
        validate_workspace_id_safe(workspace_id)

        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError(f"Invalid filename: '{filename}'")
        if encoding not in ("text", "base64"):
            raise ValueError("encoding must be 'text' or 'base64'")

        workspace_dir = WORKSPACES_DIR / workspace_id
        if not workspace_dir.exists():
            raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")

        if encoding == "base64":
            content_bytes = base64.b64decode(content)
        else:
            content_bytes = content.encode("utf-8")

        if len(content_bytes) > MAX_SINGLE_FILE_BYTES:
            raise ValueError(f"File too large: {len(content_bytes)} bytes")

        file_path = workspace_dir / filename
        file_path.write_bytes(content_bytes)

        log_audit_event("WORKSPACE_FILE_UPLOADED", {
            "workspace_id": workspace_id,
            "filename": filename,
            "size": len(content_bytes)
        })

        return {
            "ok": True,
            "workspace_id": workspace_id,
            "filename": filename,
            "size": len(content_bytes),
            "sha256": sha256_bytes(content_bytes)
        }

    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="list_workspace_files",
    description="List all files currently in a workspace."
)
def list_workspace_files(workspace_id: str) -> Dict[str, Any]:
    """Lists all files stored in a specified workspace, excluding internal metadata."""
    try:
        validate_workspace_id_safe(workspace_id)
        workspace_dir = WORKSPACES_DIR / workspace_id
        if not workspace_dir.exists():
            raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")

        files = []
        for f in workspace_dir.iterdir():
            if f.is_file() and f.name != "metadata.json":
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size
                })

        return {"ok": True, "workspace_id": workspace_id, "files": files}

    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="read_workspace_file",
    description="Read a file from workspace back to the assistant (for small text files, flags, extracted strings)."
)
def read_workspace_file(
    workspace_id: str,
    filename: str,
    encoding: str = "text",
    max_bytes: int = 50000
) -> Dict[str, Any]:
    """Reads file contents from a workspace, supporting text decoding and truncation."""
    try:
        validate_workspace_id_safe(workspace_id)

        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError(f"Invalid filename: '{filename}'")

        file_path = (WORKSPACES_DIR / workspace_id / filename).resolve()
        workspace_resolved = (WORKSPACES_DIR / workspace_id).resolve()

        if workspace_resolved not in file_path.parents and file_path != workspace_resolved:
            raise PermissionError("Path traversal blocked.")

        if not file_path.exists():
            raise FileNotFoundError(f"File '{filename}' not found in workspace.")

        max_bytes = min(max_bytes, 500000)
        content_bytes = file_path.read_bytes()[:max_bytes]
        truncated = len(file_path.read_bytes()) > max_bytes

        if encoding == "base64":
            content = base64.b64encode(content_bytes).decode("utf-8")
        else:
            content = content_bytes.decode("utf-8", errors="replace")

        return {
            "ok": True,
            "workspace_id": workspace_id,
            "filename": filename,
            "content": content,
            "encoding": encoding,
            "truncated": truncated
        }

    except Exception as e:
        return format_error_response(e)


@mcp.tool(
    name="delete_workspace",
    description="Delete a workspace and all its files."
)
def delete_workspace(workspace_id: str) -> Dict[str, Any]:
    """Permanently deletes a workspace directory."""
    try:
        validate_workspace_id_safe(workspace_id)
        workspace_dir = WORKSPACES_DIR / workspace_id
        if not workspace_dir.exists():
            raise FileNotFoundError(f"Workspace '{workspace_id}' not found.")
        shutil.rmtree(workspace_dir)
        log_audit_event("WORKSPACE_DELETED", {"workspace_id": workspace_id})
        return {"ok": True, "message": f"Workspace '{workspace_id}' deleted."}
    except Exception as e:
        return format_error_response(e)
