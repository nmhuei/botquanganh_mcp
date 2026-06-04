from typing import List, Dict, Tuple
from app.file_package import sha256_bytes

def generate_transcript(
    run_id: str,
    target: str,
    sandbox_failure: Dict,
    local_validation: Dict,
    files_info: List[Dict],  # dict keys: path, size, sha256
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    duration_ms: int
) -> Tuple[str, str]:
    """Generates a structured transcript string matching the fallback runner spec,
    along with its SHA-256 hash.
    """
    sb_lines = [
        f"attempted={str(sandbox_failure.get('attempted', False)).lower()}",
        f"reason={sandbox_failure.get('reason', '')}",
        f"error_excerpt={sandbox_failure.get('error_excerpt', '') or ''}"
    ]
    sb_section = "\n".join(sb_lines)
    
    lv_lines = [
        f"solved_locally={str(local_validation.get('solved_locally', False)).lower()}",
        f"summary={local_validation.get('summary', '')}"
    ]
    lv_section = "\n".join(lv_lines)
    
    file_lines = []
    for f in files_info:
        file_lines.append(f"{f['path']} size={f['size']} sha256={f['sha256']}")
    files_section = "\n".join(file_lines)
    
    stdout_sha256 = sha256_bytes(stdout.encode('utf-8'))
    stderr_sha256 = sha256_bytes(stderr.encode('utf-8'))
    
    # Construct base transcript content
    content_parts = [
        "[RUN_ID]",
        run_id,
        "",
        "[TARGET]",
        target,
        "",
        "[SANDBOX_FAILURE]",
        sb_section,
        "",
        "[LOCAL_VALIDATION]",
        lv_section,
        "",
        "[FILES]",
        files_section,
        "",
        "[COMMAND]",
        command,
        "",
        "[STDOUT]",
        stdout,
        "",
        "[STDERR]",
        stderr,
        "",
        "[EXIT_CODE]",
        str(exit_code),
        "",
        "[DURATION_MS]",
        str(duration_ms),
        ""
    ]
    
    base_content = "\n".join(content_parts)
    
    # Compute hash of the base transcript content
    transcript_sha = sha256_bytes(base_content.encode('utf-8'))
    
    # Append HASHES section
    hashes_part = [
        "[HASHES]",
        f"stdout_sha256={stdout_sha256}",
        f"stderr_sha256={stderr_sha256}",
        f"transcript_sha256={transcript_sha}"
    ]
    
    full_transcript = base_content + "\n" + "\n".join(hashes_part) + "\n"
    
    return full_transcript, transcript_sha
