"""CTF suite MCP tools for BotQuangAnh MCP."""

from __future__ import annotations

from typing import Any, Optional

from app.ctf.triage import triage_artifact
from app.host.paths import resolve_host_path
from app.mcp_server import mcp
from app.security import format_error_response


@mcp.tool(
    name="ctf_triage_artifact",
    description=(
        "FIRST-STEP file/binary inspector. Always call this BEFORE running file, "
        "checksec, strings, readelf, objdump, or binwalk to identify a file: in one "
        "read-only call it returns the magic/format, architecture, endianness, "
        "checksec mitigations (NX, PIE, Canary, RELRO, Stripped), Shannon entropy, "
        "and suspicious strings. Do not execute the file. Only fall back to those "
        "commands via host_run_command for details this tool does not cover."
    ),
    annotations={
        "title": "Triage CTF artifact (first-step header/checksec inspector)",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_triage_artifact(
    path: str,
    calculate_entropy: bool = True,
    extract_strings: bool = True,
    strings_min_len: int = 6,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Perform fast pure-Python static triage on a host file or challenge binary."""
    try:
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("ctf_triage_artifact", chat_id)
        if rejection is not None:
            return rejection

        journal_details = {
            "path": path,
            "calculate_entropy": calculate_entropy,
            "extract_strings": extract_strings,
        }
        journal_op = _begin_workspace_journal(
            "ctf_triage_artifact", validated, journal_details
        )

        try:
            resolved_path = resolve_host_path(
                path,
                must_exist=True,
                expect_directory=False,
                mode="read",
            )
            result = triage_artifact(
                resolved_path,
                calculate_entropy_flag=calculate_entropy,
                extract_strings_flag=extract_strings,
                strings_min_len=strings_min_len,
            )
        except Exception as exc:
            result = format_error_response(exc)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "ctf_triage_artifact",
            validated,
            {"path": path},
        )
        _finish_workspace_journal(
            "ctf_triage_artifact",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)
