"""CTF suite MCP tools for BotQuangAnh MCP.

Includes:
- ctf_triage_artifact: First-step static binary/file inspector (ELF/PE headers, checksec, entropy, strings)
- ctf_transform: Offline byte/text encoding, decoding, compression, and XOR
- ctf_pattern: De Bruijn cyclic pattern generator & crash offset locator for PWN
- ctf_hash_tool: Offline cryptographic hash identifier and digest calculator
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from app.ctf.hash_tool import compute_hashes, identify_hash
from app.ctf.pattern import cyclic_create, cyclic_offset
from app.ctf.transforms import transform
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


@mcp.tool(
    name="ctf_transform",
    description=(
        "Run offline byte and text transformations without running shell commands. "
        "Supported operations: 'base64_encode', 'base64_decode', 'hex_encode', 'hex_decode', "
        "'url_encode', 'url_decode', 'gzip_compress', 'gzip_decompress', 'zlib_compress', "
        "'zlib_decompress', 'rot13', 'xor_hex'. Provide exactly one input carrier: either "
        "'input_text' (for UTF-8 string) or 'input_base64' (for binary bytes). 'key_hex' is "
        "required for 'xor_hex'. Returns lossless output in base64 and utf-8 text (if valid)."
    ),
    annotations={
        "title": "CTF transform (offline encoding/crypto transform)",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_transform(
    operation: str,
    input_text: Optional[str] = None,
    input_base64: Optional[str] = None,
    key_hex: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Perform bounded offline byte/text transformation (base64, hex, url, rot13, gzip, zlib, xor)."""
    try:
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("ctf_transform", chat_id)
        if rejection is not None:
            return rejection

        journal_details = {
            "operation": operation,
            "has_input_text": input_text is not None,
            "has_input_base64": input_base64 is not None,
            "has_key_hex": key_hex is not None,
        }
        journal_op = _begin_workspace_journal(
            "ctf_transform", validated, journal_details
        )

        try:
            raw_result = transform(
                operation,
                input_text=input_text,
                input_base64=input_base64,
                key_hex=key_hex,
            )
            out_bytes = base64.b64decode(raw_result["output_base64"])
            result: dict[str, Any] = {
                "ok": True,
                "operation": operation,
                "output_bytes": len(out_bytes),
                "output_base64": raw_result["output_base64"],
                "output_text": raw_result.get("output_text"),
            }
        except Exception as exc:
            result = format_error_response(exc)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "ctf_transform",
            validated,
            {"operation": operation},
        )
        _finish_workspace_journal(
            "ctf_transform",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="ctf_pattern",
    description=(
        "PWN/Reverse engineering cyclic pattern generator and crash offset locator (De Bruijn sequence). "
        "Compatible with pwntools cyclic() and cyclic_find(). "
        "- To create a pattern: action='create', length=N (e.g. 128, 256, 1024), width=4 (32-bit) or 8 (64-bit). "
        "- To find an offset: action='offset', value='caaa' or '0x61616163' (hex address or crash string), width=4 (or 8)."
    ),
    annotations={
        "title": "CTF cyclic pattern generator and offset finder",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_pattern(
    action: str,
    length: int = 128,
    value: Optional[str] = None,
    width: int = 4,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Generate De Bruijn cyclic pattern or calculate offset to return address/EIP/RIP."""
    try:
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("ctf_pattern", chat_id)
        if rejection is not None:
            return rejection

        journal_details = {"action": action, "length": length, "width": width}
        journal_op = _begin_workspace_journal(
            "ctf_pattern", validated, journal_details
        )

        try:
            act = action.strip().lower()
            if act == "create":
                pattern = cyclic_create(length=length, width=width)
                result: dict[str, Any] = {
                    "ok": True,
                    "action": "create",
                    "length": len(pattern),
                    "width": width,
                    "pattern": pattern,
                }
            elif act == "offset":
                if not value:
                    raise ValueError("action='offset' requires a non-empty 'value'.")
                offset = cyclic_offset(value=value, width=width)
                result = {
                    "ok": offset >= 0,
                    "action": "offset",
                    "value": value,
                    "width": width,
                    "offset": offset,
                    "found": offset >= 0,
                    "message": f"Offset is {offset}" if offset >= 0 else "Pattern subsequence not found",
                }
            else:
                raise ValueError("action must be 'create' or 'offset'.")
        except Exception as exc:
            result = format_error_response(exc)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "ctf_pattern",
            validated,
            {"action": action},
        )
        _finish_workspace_journal(
            "ctf_pattern",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="ctf_hash_tool",
    description=(
        "Fast offline cryptographic hash identifier and digest calculator for CTF. "
        "- action='identify': Analyzes value (hex, crypt, bcrypt, base64) and identifies candidate algorithms (MD5, SHA-1, SHA-256, NTLM, bcrypt, etc.) with hashcat/john modes. "
        "- action='compute': Calculates standard digests (MD5, SHA-1, SHA-256, SHA-512, NTLM, CRC-32) of value."
    ),
    annotations={
        "title": "CTF hash identifier and digest calculator",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_hash_tool(
    action: str,
    value: str,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Identify hash types or compute MD5/SHA1/SHA256/SHA512/NTLM/CRC32 digests."""
    try:
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("ctf_hash_tool", chat_id)
        if rejection is not None:
            return rejection

        journal_details = {"action": action}
        journal_op = _begin_workspace_journal(
            "ctf_hash_tool", validated, journal_details
        )

        try:
            act = action.strip().lower()
            if act == "identify":
                candidates = identify_hash(value)
                result: dict[str, Any] = {
                    "ok": True,
                    "action": "identify",
                    "input_length": len(value.strip()),
                    "candidates": candidates,
                    "candidate_count": len(candidates),
                }
            elif act == "compute":
                hashes = compute_hashes(value)
                result = {
                    "ok": True,
                    "action": "compute",
                    "input_bytes": len(value.encode("utf-8")),
                    "hashes": hashes,
                }
            else:
                raise ValueError("action must be 'identify' or 'compute'.")
        except Exception as exc:
            result = format_error_response(exc)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "ctf_hash_tool",
            validated,
            {"action": action},
        )
        _finish_workspace_journal(
            "ctf_hash_tool",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="auto_download_ctf_challenge",
    description=(
        "Initialize standardized CTF challenge harness (challenge/, script/, solver/) "
        "and optionally download/extract remote challenge files. "
        "Creates metadata.json, challenge/NOTE.md, script/analysis.md, and boilerplate solver/solve.py. "
        "If a URL is provided, downloads and safely unpacks archives (.zip/.tar.gz), then runs "
        "ctf_triage_artifact automatically on the downloaded binary."
    ),
    annotations={
        "title": "Auto-download CTF challenge and initialize 3-folder harness",
        "readOnlyHint": False,
        "openWorldHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
    },
)
def auto_download_ctf_challenge(
    name: str,
    category: str = "pwn",
    url: Optional[str] = None,
    description: Optional[str] = None,
    target: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Scaffold standard 3-folder CTF harness (challenge/, script/, solver/) and optionally fetch challenge files."""
    try:
        from pathlib import Path
        from app.ctf.challenge_harness import setup_ctf_harness
        from app.host.paths import host_workspace_dir
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("auto_download_ctf_challenge", chat_id)
        if rejection is not None:
            return rejection

        target_ws: Path
        if chat_id is not None and validated:
            from app.tools.workspace_tools import _chat_root
            target_ws = _chat_root() / validated
        else:
            import re
            clean_n = re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("-_") or "chal"
            clean_cat = category.lower().strip() if category else "pwn"
            folder_candidate = clean_n if clean_n.startswith(f"{clean_cat}_") else f"{clean_cat}_{clean_n}"
            target_ws = host_workspace_dir() / folder_candidate

        journal_details = {"name": name, "category": category, "has_url": url is not None}
        journal_op = _begin_workspace_journal(
            "auto_download_ctf_challenge", validated, journal_details
        )

        try:
            result = setup_ctf_harness(
                workspace_dir=target_ws,
                name=name,
                category=category,
                url=url,
                description=description,
                target=target,
            )
        except Exception as exc:
            result = format_error_response(exc)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "auto_download_ctf_challenge",
            validated,
            {"name": name, "category": category},
        )
        _finish_workspace_journal(
            "auto_download_ctf_challenge",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)


@mcp.tool(
    name="ctf_crypto_playbook",
    description=(
        "Query the BQA Extreme Cryptography Playbook and Attack Router Matrix. "
        "Use this tool to find the exact attack vector, mathematical preconditions, "
        "equations, and verification method for RSA, ECC, lattices, PRNG, AES, and hashes. "
        "Pass 'query' (e.g., 'wiener', 'coppersmith', 'biased nonce', 'smart', 'lcg', 'gcm') "
        "or 'section' ('phases', 'matrix', 'rsa', 'ecc', 'lattice', 'audit') to get deterministic guidance. "
        "Leaving arguments empty returns the 5-phase protocol and full category overview."
    ),
    annotations={
        "title": "Query BQA Cryptography Playbook & Attack Router Matrix",
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
def ctf_crypto_playbook(
    query: Optional[str] = None,
    section: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Look up deterministic attack vectors and formulas from BQA Extreme Crypto Playbook."""
    try:
        from app.ctf.crypto_playbook import query_crypto_playbook
        from app.tools.host import (
            _begin_workspace_journal,
            _finish_workspace_journal,
            _guard_chat_id,
            _record_tool_call,
        )

        validated, rejection = _guard_chat_id("ctf_crypto_playbook", chat_id)
        if rejection is not None:
            return rejection

        journal_details = {"query": query, "section": section}
        journal_op = _begin_workspace_journal(
            "ctf_crypto_playbook", validated, journal_details
        )

        result = query_crypto_playbook(query=query, section=section)

        ok = isinstance(result, dict) and bool(result.get("ok", False))
        _record_tool_call(
            "ctf_crypto_playbook",
            validated,
            {"query": query, "section": section},
        )
        _finish_workspace_journal(
            "ctf_crypto_playbook",
            validated,
            journal_op,
            ok=ok,
            details=journal_details,
        )
        return result
    except Exception as exc:
        return format_error_response(exc)


