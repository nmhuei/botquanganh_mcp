import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.mcp_server import mcp
import app.config
from app.logging_audit import log_audit_event
from app.security import format_error_response

# Helper to validate and resolve paths
def resolve_agent_path(user_path: str) -> Path:
    p = Path(user_path).expanduser()
    if not p.is_absolute():
        p = app.config.AGENT_WORKSPACE_DIR / p
    resolved = p.resolve()
    
    if app.config.AGENT_RESTRICT_TO_WORKSPACE:
        try:
            resolved.relative_to(app.config.AGENT_WORKSPACE_DIR)
        except ValueError:
            raise PermissionError(f"Access denied. Path '{user_path}' is outside the agent workspace directory '{app.config.AGENT_WORKSPACE_DIR}'.")
            
    return resolved

@mcp.tool(
    name="agent_list_directory",
    description="List contents of a directory on the local machine workspace, showing file names, sizes, and whether they are directories."
)
def agent_list_directory(path: str = ".") -> Dict[str, Any]:
    """Lists files and folders inside the specified directory."""
    try:
        resolved = resolve_agent_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
            
        items = []
        for item in resolved.iterdir():
            is_dir = item.is_dir()
            size = 0 if is_dir else item.stat().st_size
            items.append({
                "name": item.name,
                "is_directory": is_dir,
                "size_bytes": size
            })
            
        return {
            "ok": True,
            "path": path,
            "items": sorted(items, key=lambda x: (not x["is_directory"], x["name"]))
        }
    except Exception as e:
        return format_error_response(e)

@mcp.tool(
    name="agent_read_file",
    description="Read the contents of a text file on the local machine. Optional line range (1-indexed, inclusive) can be specified."
)
def agent_read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
    """Reads content from a local file. Supports optional line range (1-indexed, inclusive)."""
    try:
        resolved = resolve_agent_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not resolved.is_file():
            raise ValueError(f"Path is not a file: {path}")
            
        # Check file size
        file_size = resolved.stat().st_size
        if file_size > app.config.MAX_SINGLE_FILE_BYTES:
            raise ValueError(f"File size exceeds limit: {file_size} bytes (max: {app.config.MAX_SINGLE_FILE_BYTES})")
            
        content = resolved.read_text(encoding="utf-8", errors="replace")
        
        # If line range is specified, slice the lines
        if start_line is not None or end_line is not None:
            lines = content.splitlines()
            total_lines = len(lines)
            
            s = start_line if start_line is not None else 1
            e = end_line if end_line is not None else total_lines
            
            # Convert to 0-indexed
            s_idx = max(0, s - 1)
            e_idx = min(total_lines, e)
            
            sliced_lines = lines[s_idx:e_idx]
            content = "\n".join(sliced_lines)
            
            return {
                "ok": True,
                "path": path,
                "content": content,
                "start_line": s,
                "end_line": e,
                "total_lines": total_lines,
                "sliced": True
            }
            
        return {
            "ok": True,
            "path": path,
            "content": content,
            "total_lines": len(content.splitlines()),
            "sliced": False
        }
    except Exception as e:
        return format_error_response(e)

@mcp.tool(
    name="agent_write_file",
    description="Write/create a file on the local machine with the given content."
)
def agent_write_file(path: str, content: str) -> Dict[str, Any]:
    """Write or overwrite a file with the given content."""
    try:
        resolved = resolve_agent_path(path)
        # Create parent directories if they don't exist
        resolved.parent.mkdir(parents=True, exist_ok=True)
        
        resolved.write_text(content, encoding="utf-8")
        log_audit_event("AGENT_WRITE_FILE", {"path": str(resolved), "size": len(content)})
        return {"ok": True, "message": f"Successfully wrote file '{path}'"}
    except Exception as e:
        return format_error_response(e)

@mcp.tool(
    name="agent_edit_file",
    description="Edit a file on the local machine by replacing a unique block of text (target) with replacement text."
)
def agent_edit_file(path: str, target: str, replacement: str) -> Dict[str, Any]:
    """Edit a local file by replacing a unique block of text (target) with replacement text."""
    try:
        resolved = resolve_agent_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not resolved.is_file():
            raise ValueError(f"Path is not a file: {path}")
            
        content = resolved.read_text(encoding="utf-8")
        
        # Check if target is unique
        count = content.count(target)
        if count == 0:
            raise ValueError("Target content not found in the file.")
        if count > 1:
            raise ValueError("Target content is not unique (found multiple occurrences). Please specify a unique block of text.")
            
        new_content = content.replace(target, replacement)
        resolved.write_text(new_content, encoding="utf-8")
        
        log_audit_event("AGENT_EDIT_FILE", {"path": str(resolved)})
        return {"ok": True, "message": f"Successfully edited file '{path}'"}
    except Exception as e:
        return format_error_response(e)

@mcp.tool(
    name="agent_grep_search",
    description="Perform a text search recursively across files in a local directory, returning match locations and lines."
)
def agent_grep_search(query: str, path: str = ".") -> Dict[str, Any]:
    """Search for the search term (query) in files within the specified directory path."""
    try:
        resolved = resolve_agent_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Search path not found: {path}")
            
        results = []
        # Walk through files recursively, search content
        for root, dirs, files in os.walk(resolved):
            # Exclude virtual environments, git, caches etc.
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", "node_modules", ".pytest_cache")]
            for file in files:
                file_path = Path(root) / file
                # Skip files larger than 1MB or binary files
                if file_path.stat().st_size > 1000000:
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if query in line:
                                # Show path relative to AGENT_WORKSPACE_DIR if possible
                                try:
                                    relative_path = file_path.relative_to(app.config.AGENT_WORKSPACE_DIR)
                                except ValueError:
                                    relative_path = file_path
                                results.append({
                                    "path": str(relative_path),
                                    "line_number": line_num,
                                    "line_content": line.strip()
                                })
                                if len(results) >= 100:  # limit to 100 results
                                    break
                except Exception:
                    pass
                if len(results) >= 100:
                    break
            if len(results) >= 100:
                break
                
        return {
            "ok": True,
            "query": query,
            "results": results
        }
    except Exception as e:
        return format_error_response(e)

@mcp.tool(
    name="agent_run_command",
    description="Execute a shell command on the host machine. Run commands relative to the workspace directory. Returns stdout, stderr, and exit code."
)
def agent_run_command(command: str, cwd: Optional[str] = None, timeout_seconds: int = 60) -> Dict[str, Any]:
    """Runs a shell command on the host machine. Run commands relative to the workspace directory."""
    try:
        if cwd:
            resolved_cwd = resolve_agent_path(cwd)
        else:
            resolved_cwd = app.config.AGENT_WORKSPACE_DIR
            
        if not resolved_cwd.exists() or not resolved_cwd.is_dir():
            raise ValueError(f"Working directory does not exist or is not a directory: {cwd}")

        from app.tools.shell import _validate_command_safe_enough
        _validate_command_safe_enough(command)

        log_audit_event("AGENT_RUN_COMMAND", {"command": command, "cwd": str(resolved_cwd)})
        
        # Run command using subprocess
        result = subprocess.run(
            command,
            shell=True,
            cwd=resolved_cwd,
            capture_output=True,
            timeout=timeout_seconds
        )
        
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        
        # Truncate output if too large
        if len(stdout) > app.config.MAX_OUTPUT_BYTES:
            stdout = stdout[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"
        if len(stderr) > app.config.MAX_OUTPUT_BYTES:
            stderr = stderr[:app.config.MAX_OUTPUT_BYTES] + "\n... [TRUNCATED]"
            
        return {
            "ok": True,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT", "message": f"Command timed out after {timeout_seconds} seconds"}}
    except Exception as e:
        return format_error_response(e)
