"""Host execution core used by the MCP host tool profile.

This package contains no MCP decorators.  The public MCP surface lives in
``app.tools.host`` and delegates to these modules.
"""

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

__all__ = [
    "append_text_file",
    "execute_host_command",
    "inspect_host_command",
    "list_directory",
    "make_directory",
    "read_text_file",
    "replace_text_in_file",
    "search_text",
    "write_text_file",
]
