import base64
import hashlib
from pathlib import Path
from typing import List, Tuple
from app.schemas import FileEntry
from app.config import MAX_CODE_BYTES, MAX_SINGLE_FILE_BYTES, ARTIFACTS_DIR
from app.security import validate_relative_path

def validate_and_decode_file(file: FileEntry) -> bytes:
    """Validates the file path, verifies size limits, and decodes the content based on encoding."""
    # Enforce relative path rules
    validate_relative_path(file.path)
    
    # Resolve using artifact store if referenced
    if file.artifact_id is not None:
        if not file.artifact_id.startswith("art_") or ".." in file.artifact_id or "/" in file.artifact_id or "\\" in file.artifact_id:
            raise ValueError(f"Invalid artifact_id format: '{file.artifact_id}'")
        
        artifact_path = ARTIFACTS_DIR / file.artifact_id
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact '{file.artifact_id}' not found in storage.")
        content_bytes = artifact_path.read_bytes()
    else:
        # Decode contents
        if file.encoding == "base64":
            try:
                content_bytes = base64.b64decode(file.content)
            except Exception as e:
                raise ValueError(f"Failed to decode base64 content for file '{file.path}': {str(e)}")
        elif file.encoding == "text":
            content_bytes = file.content.encode("utf-8")
        else:
            raise ValueError(f"Unsupported file encoding '{file.encoding}' for file '{file.path}'")
        
    # Check individual file size limit
    if len(content_bytes) > MAX_SINGLE_FILE_BYTES:
        raise ValueError(
            f"File '{file.path}' size ({len(content_bytes)} bytes) "
            f"exceeds MAX_SINGLE_FILE_BYTES ({MAX_SINGLE_FILE_BYTES} bytes)."
        )
        
    return content_bytes

def check_total_size_and_validate(files: List[FileEntry]) -> List[Tuple[str, bytes]]:
    """Validates all files in the package, checks package-wide limits, and returns list of path-bytes pairs."""
    decoded_files = []
    total_size = 0
    seen_paths = set()

    for file in files:
        if file.path in seen_paths:
            raise ValueError(f"Duplicate file path '{file.path}' is not allowed.")
        seen_paths.add(file.path)

        content_bytes = validate_and_decode_file(file)
        decoded_files.append((file.path, content_bytes))
        total_size += len(content_bytes)
        
    if total_size > MAX_CODE_BYTES:
        raise ValueError(
            f"Total package size ({total_size} bytes) "
            f"exceeds MAX_CODE_BYTES ({MAX_CODE_BYTES} bytes)."
        )
        
    return decoded_files

def write_files(run_input_dir: Path, decoded_files: List[Tuple[str, bytes]]) -> None:
    """Securely writes decoded file payloads to the run directory, ensuring no escapes."""
    # Resolve the destination directory to make path comparisons robust
    run_input_dir_resolved = run_input_dir.resolve()
    run_input_dir_resolved.mkdir(parents=True, exist_ok=True)

    for rel_path, content_bytes in decoded_files:
        # Construct the absolute path
        target_path = (run_input_dir_resolved / rel_path).resolve()
        
        # Verify it remains strictly within the run input directory
        # Using commonpath is safer than simple prefix string matching
        try:
            # If target_path is not under run_input_dir_resolved, this raises ValueError or returns false
            if target_path != run_input_dir_resolved and run_input_dir_resolved not in target_path.parents:
                raise PermissionError(f"Security block: File '{rel_path}' attempts to escape run directory.")
        except Exception:
            raise PermissionError(f"Security block: Invalid path construction for '{rel_path}'.")
            
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content_bytes)

def sha256_bytes(data: bytes) -> str:
    """Computes SHA-256 hash of byte content."""
    return hashlib.sha256(data).hexdigest()

def sha256_file(path: Path) -> str:
    """Computes SHA-256 hash of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()
