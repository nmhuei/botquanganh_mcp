from __future__ import annotations

from typing import Any, Optional

from app.host.executor import execute_host_command
from app.host.files import (
    append_text_file,
    list_directory,
    make_directory,
    read_text_file,
    replace_text_in_file,
    search_text,
    write_text_file,
)
from app.host.policy import inspect_host_command
from app.mcp_server import mcp
from app.security import format_error_response


@mcp.tool(
    name="host_list_directory",
    description=(
        "List files and directories on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads)."
    ),
)
def host_list_directory(path: str = ".", max_entries: int = 500) -> dict[str, Any]:
    try:
        return list_directory(path, max_entries=max_entries)
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_read_file",
    description=(
        "Read a UTF-8 text file from the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). Absolute paths "
        "within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> dict[str, Any]:
    try:
        return read_text_file(
            path,
            start_line=start_line,
            end_line=end_line,
            max_bytes=max_bytes,
        )
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_write_file",
    description=(
        "Create or overwrite a UTF-8 text file on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads) to keep the host tidy. "
        "Absolute paths within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_write_file(
    path: str,
    content: str,
    overwrite: bool = True,
    create_parents: bool = True,
) -> dict[str, Any]:
    try:
        return write_text_file(
            path,
            content,
            overwrite=overwrite,
            create_parents=create_parents,
        )
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_replace_in_file",
    description=(
        "Replace text in a host file and require the expected number of matches "
        "before writing."
    ),
)
def host_replace_in_file(
    path: str,
    old: str,
    new: str,
    expected_count: int = 1,
) -> dict[str, Any]:
    try:
        return replace_text_in_file(
            path,
            old,
            new,
            expected_count=expected_count,
        )
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_append_file",
    description="Append UTF-8 text to a file on the host machine.",
)
def host_append_file(path: str, content: str) -> dict[str, Any]:
    try:
        return append_text_file(path, content)
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_make_directory",
    description=(
        "Create a directory on the host machine. Relative paths are resolved "
        "from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). Absolute paths "
        "within HOST_WORKSPACE_DIR are also supported."
    ),
)
def host_make_directory(path: str, parents: bool = True) -> dict[str, Any]:
    try:
        return make_directory(path, parents=parents)
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_search_text",
    description=(
        "Search text recursively across host files while excluding common build, "
        "VCS, virtual-environment, and dependency directories."
    ),
)
def host_search_text(
    query: str,
    path: str = ".",
    case_sensitive: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    try:
        return search_text(
            query,
            path=path,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_check_command",
    description=(
        "Inspect a shell command against the server-side host policy without "
        "executing it. There is no caller-supplied approval bypass."
    ),
)
def host_check_command(command: str) -> dict[str, Any]:
    try:
        return {"ok": True, **inspect_host_command(command)}
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="host_run_command",
    description=(
        "Execute a shell command directly on the user's host machine. Relative cwd "
        "values are resolved from the default directory (HOST_DEFAULT_DIR, e.g. ~/Downloads). "
        "The default working directory is HOST_DEFAULT_DIR. Destructive commands are blocked."
    ),
)
def host_run_command(
    command: str,
    timeout_seconds: int = 30,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    try:
        return execute_host_command(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return format_error_response(exc)
