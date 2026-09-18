"""Tests for the pure-Python CTF triage engine and the ctf_triage_artifact tool.

Covers (per the design):
- Shannon entropy classification (text / binary / packed)
- Magic-bytes format detection
- ELF parsing + checksec (NX, PIE via DF_1_PIE, Canary via string tables,
  RELRO, Stripped) using a deterministic synthetic-ELF builder
- Suspicious-string extraction (flags, URLs, shell calls, format strings)
- Tool security boundaries (workspace restriction / path traversal / chat gate)
- The "harness": server instructions + tool description steer the LLM to call
  this tool first instead of shelling out to file/checksec/strings/readelf.
"""

import asyncio
import os
import struct
from pathlib import Path

import pytest

import app.config
from app.ctf.triage import (
    calculate_entropy,
    detect_magic,
    extract_suspicious_strings,
    parse_elf,
    triage_artifact,
)
from app.tools.ctf_suite import ctf_triage_artifact

# ------------------------------------------------------------- ELF constants
_DT_NULL = 0
_DT_FLAGS = 30
_DT_FLAGS_1 = 0x6FFFFFFB
_DF_1_NOW = 0x00000001
_DF_1_PIE = 0x08000000
_PT_DYNAMIC = 2
_PT_GNU_STACK = 0x6474E551
_PT_GNU_RELRO = 0x6474E552
_PF_X = 0x1
_PF_W = 0x2
_MACH_X86_64 = 0x3E
_ET_EXEC = 2
_ET_DYN = 3


def _elf64(
    *,
    e_type=_ET_DYN,
    machine=_MACH_X86_64,
    flags=None,
    flags1=None,
    gnu_stack=None,
    relro=False,
    sections=None,
) -> bytes:
    """Build a deterministic little-endian 64-bit ELF for unit tests.

    ``sections`` maps section name -> raw bytes. A ``.shstrtab`` section is
    added automatically and referenced by e_shstrndx.
    """
    sections = dict(sections or {})
    ehsize, phentsize, shentsize = 64, 56, 64

    dyn = []
    if flags is not None:
        dyn.append((_DT_FLAGS, flags))
    if flags1 is not None:
        dyn.append((_DT_FLAGS_1, flags1))
    has_dyn = bool(dyn)
    if has_dyn:
        dyn.append((_DT_NULL, 0))

    phdrs = []
    if has_dyn:
        phdrs.append("DYN")
    if gnu_stack is not None:
        phdrs.append("STACK")
    if relro:
        phdrs.append("RELRO")
    n_ph = len(phdrs)
    dyn_filesz = len(dyn) * 16 if has_dyn else 0
    dyn_off = ehsize + n_ph * phentsize

    names = list(sections.keys())
    shstr_names = names + [".shstrtab"]
    shstrtab = b"\x00" + b"".join(n.encode("ascii") + b"\x00" for n in shstr_names)
    name_off: dict[str, int] = {}
    pos = 1  # shstrtab has a leading NUL at index 0
    for n in shstr_names:
        name_off[n] = pos
        pos += len(n) + 1

    sec_start = dyn_off + (dyn_filesz if has_dyn else 0)
    sec_records: dict[str, tuple[int, int]] = {}
    off = sec_start
    for n, data in sections.items():
        sec_records[n] = (off, len(data))
        off += len(data)
    shstr_offset, shstr_size = off, len(shstrtab)
    off += shstr_size
    shoff = off
    n_sh = 1 + len(names) + 1  # NULL + user sections + .shstrtab
    shstrndx = 1 + len(names)

    def shdr(name_idx, sh_type, sh_flags, sh_addr, sh_offset, sh_size) -> bytes:
        return struct.pack(
            "<IIQQQQIIQQ",
            name_idx, sh_type, sh_flags, sh_addr, sh_offset, sh_size, 0, 0, 1, 0,
        )

    shdrs = bytearray()
    shdrs += shdr(0, 0, 0, 0, 0, 0)  # NULL section
    for n in names:
        s_off, s_size = sec_records[n]
        if n == ".symtab":
            sh_type = 2  # SHT_SYMTAB
        elif n in (".strtab", ".dynstr"):
            sh_type = 3  # SHT_STRTAB
        else:
            sh_type = 1  # SHT_PROGBITS
        shdrs += shdr(name_off[n], sh_type, 0, 0, s_off, s_size)
    shdrs += shdr(name_off[".shstrtab"], 3, 0, 0, shstr_offset, shstr_size)

    buf = bytearray()
    buf += b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8
    buf += struct.pack(
        "<HHIQQQIHHHHHH",
        e_type, machine, 1, 0x1000, ehsize, shoff, 0,
        ehsize, phentsize, n_ph, shentsize, n_sh, shstrndx,
    )
    assert len(buf) == ehsize
    for tag in phdrs:
        if tag == "DYN":
            buf += struct.pack(
                "<IIQQQQQQ", _PT_DYNAMIC, 0, dyn_off, 0, 0, dyn_filesz, dyn_filesz, 8
            )
        elif tag == "STACK":
            buf += struct.pack(
                "<IIQQQQQQ", _PT_GNU_STACK, gnu_stack, 0, 0, 0, 0, 0, 8
            )
        elif tag == "RELRO":
            buf += struct.pack(
                "<IIQQQQQQ", _PT_GNU_RELRO, _PF_W, 0, 0, 0, 0, 0, 8
            )
    while len(buf) < dyn_off:
        buf += b"\x00"
    for d_tag, d_val in dyn:
        buf += struct.pack("<qQ", d_tag, d_val)
    while len(buf) < sec_start:
        buf += b"\x00"
    for n in names:
        buf += sections[n]
    buf += shstrtab
    while len(buf) < shoff:
        buf += b"\x00"
    buf += shdrs
    return bytes(buf)


# ------------------------------------------------------------------- entropy


def test_entropy_empty_file():
    result = calculate_entropy(b"")
    assert result["score"] == 0.0
    assert result["assessment"] == "empty_file"


def test_entropy_repetitive_is_text_class():
    result = calculate_entropy(b"A" * 4096)
    assert result["score"] < 6.0
    assert result["assessment"] == "normal_text"


def test_entropy_random_is_packed_class():
    import os

    result = calculate_entropy(os.urandom(65536))
    assert result["score"] > 7.2
    assert result["assessment"] == "packed_or_encrypted"


def test_entropy_thresholds_are_design_buckets():
    assert calculate_entropy(b"hello world hello world")["assessment"] == "normal_text"
    # 6.0 <= H <= 7.2 -> normal_binary; 7.2 < H -> packed_or_encrypted
    mid = calculate_entropy(os.urandom(16) + b"\x00" * 65536)
    assert mid["assessment"] in {"normal_text", "normal_binary", "packed_or_encrypted"}


# --------------------------------------------------------------------- magic


@pytest.mark.parametrize(
    "header,expected_format,expected_category",
    [
        (b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 12, "ELF Executable / Library", "executable"),
        (b"MZ" + b"\x00" * 16, "PE Executable (Windows DOS/PE)", "executable"),
        (b"PK\x03\x04" + b"\x00" * 8, "ZIP Archive (ZIP/APK/JAR/DOCX)", "archive"),
        (b"\x1f\x8b\x08\x00" + b"\x00" * 8, "Gzip Compressed Data", "archive"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "PNG Image", "media"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "JPEG Image", "media"),
        (b"\xd4\xc3\xb2\xa1" + b"\x00" * 8, "PCAP Capture (Little Endian)", "network"),
        (b"%PDF-1.4" + b"\x00" * 8, "PDF Document", "document"),
        (b"SQLite format 3\x00" + b"\x00" * 4, "SQLite 3 Database", "database"),
    ],
)
def test_detect_magic_signatures(header, expected_format, expected_category):
    result = detect_magic(header, len(header))
    assert result["format"] == expected_format
    assert result["category"] == expected_category


def test_detect_magic_empty():
    result = detect_magic(b"", 0)
    assert result["format"] == "Empty File"
    assert result["category"] == "empty"


def test_detect_magic_tar_at_offset_257():
    header = bytearray(262)
    header[257:262] = b"ustar"
    result = detect_magic(bytes(header), len(header))
    assert result["format"] == "POSIX Tar Archive"
    assert result["category"] == "archive"


def test_detect_magic_plain_text():
    result = detect_magic(b"#!/usr/bin/env python3\nprint('hi')\n" * 32, 2048)
    assert result["category"] == "text"


def test_detect_magic_unknown_binary():
    result = detect_magic(b"\x01\x02\x03\x04\x05\x06\x07\x08" * 16, 128)
    assert result["category"] == "unknown"


# ----------------------------------------------------------------- ELF parser


def test_elf_pie_requires_df1_pie_flag():
    # ET_DYN + DF_1_PIE -> PIE executable
    pie = _elf64(e_type=_ET_DYN, flags1=_DF_1_PIE)
    assert parse_elf(pie)["checksec"]["pie"] is True
    assert parse_elf(pie)["kind"] == "pie executable"

    # ET_DYN without DF_1_PIE -> shared object, NOT pie
    shared = _elf64(e_type=_ET_DYN, flags1=_DF_1_NOW)
    assert parse_elf(shared)["checksec"]["pie"] is False
    assert parse_elf(shared)["kind"] == "shared object"

    # ET_DYN with no dynamic flags at all -> not pie
    bare_dyn = _elf64(e_type=_ET_DYN)
    assert parse_elf(bare_dyn)["checksec"]["pie"] is False


def test_elf_exec_is_never_pie():
    result = parse_elf(_elf64(e_type=_ET_EXEC, flags1=_DF_1_PIE))
    assert result["checksec"]["pie"] is False
    assert result["kind"] == "executable"


def test_elf_nx_follows_gnu_stack_pf_x():
    # PF_X on GNU_STACK -> executable stack -> NX disabled
    assert parse_elf(_elf64(gnu_stack=_PF_X))["checksec"]["nx"] is False
    # W-only stack -> NX enabled
    assert parse_elf(_elf64(gnu_stack=_PF_W))["checksec"]["nx"] is True
    # no GNU_STACK segment -> kernel treats stack as executable
    assert parse_elf(_elf64())["checksec"]["nx"] is False


def test_elf_relro_full_partial_none():
    full = parse_elf(_elf64(relro=True, flags1=_DF_1_NOW))
    assert full["checksec"]["relro"] == "Full RELRO"

    partial = parse_elf(_elf64(relro=True))
    assert partial["checksec"]["relro"] == "Partial RELRO"

    none = parse_elf(_elf64())
    assert none["checksec"]["relro"] == "No RELRO"


def test_elf_canary_from_string_tables_only():
    # __stack_chk_fail present in .dynstr -> canary found
    with_canary = parse_elf(
        _elf64(sections={".dynstr": b"\x00__stack_chk_fail\x00libc_start_main\x00"})
    )
    assert with_canary["checksec"]["canary"] is True

    # same symbol NOT in a string table (just stray bytes) -> canary not found
    stray = _elf64(sections={".dynstr": b"\x00printf\x00"}) + b"__stack_chk_fail"
    assert parse_elf(stray)["checksec"]["canary"] is False


def test_elf_stripped_tracks_symtab():
    assert parse_elf(_elf64(sections={".symtab": b"\x00" * 24}))["checksec"]["stripped"] is False
    assert parse_elf(_elf64())["checksec"]["stripped"] is True


def test_elf_arch_and_endian():
    result = parse_elf(_elf64(e_type=_ET_DYN, machine=_MACH_X86_64, flags1=_DF_1_PIE))
    assert result["arch_id"] == "amd64"
    assert result["arch_display"] == "x86-64"
    assert result["endian"] == "little"
    assert result["class"] == "64-bit"


def test_parse_elf_rejects_non_elf():
    assert parse_elf(b"MZ" + b"\x00" * 64) is None
    assert parse_elf(b"\x7fEL") is None


# ---------------------------------------------------------- suspicious strings


def test_strings_extract_flag_url_shell_and_format():
    payload = (
        b"please open https://example.com/flag here\n"
        b"run /bin/sh -c id now\n"
        b"leak the %s %p %x please\n"
        b"win: CTF{flag_here_123}\n"
    )
    found = extract_suspicious_strings(payload)
    joined = "\n".join(found)
    assert "https://example.com/flag" in joined
    assert "/bin/sh" in joined
    assert any(tok in joined for tok in ("%s", "%p", "%x"))
    assert "CTF{flag_here_123}" in joined


def test_strings_respects_max_count():
    payload = b"\n".join(b"/bin/sh variant number %d" % i for i in range(200))
    found = extract_suspicious_strings(payload, max_count=10)
    assert len(found) <= 10


# --------------------------------------------------------------- triage artifact


def test_triage_artifact_builds_design_schema(tmp_path: Path):
    elf = _elf64(
        e_type=_ET_DYN,
        flags1=_DF_1_PIE | _DF_1_NOW,
        gnu_stack=_PF_W,
        relro=True,
        sections={".dynstr": b"\x00__stack_chk_fail\x00", ".symtab": b"\x00" * 24},
    )
    target = tmp_path / "sample.bin"
    target.write_bytes(elf)

    result = triage_artifact(target, extract_strings_flag=False)

    assert result["ok"] is True
    assert result["format"] == "ELF 64-bit LSB pie executable, x86-64"
    assert result["security"] == {
        "arch": "amd64",
        "endian": "little",
        "nx": True,
        "pie": True,
        "canary": True,
        "relro": "Full",
        "stripped": False,
    }
    assert result["entropy"]["score"] > 0


def test_triage_artifact_missing_file(tmp_path: Path):
    result = triage_artifact(tmp_path / "nope.bin")
    assert result["ok"] is False
    assert "error" in result


# ------------------------------------------------- real binaries (when present)


@pytest.mark.skipif(not Path("/bin/ls").is_file(), reason="no /bin/ls")
def test_real_pie_binary_matches_checksec():
    result = triage_artifact(Path("/bin/ls"), extract_strings_flag=False)
    assert result["ok"] is True
    assert "pie executable" in result["format"]
    assert result["security"]["pie"] is True
    assert result["security"]["nx"] is True


@pytest.mark.skipif(not Path("/usr/bin/python3").is_file(), reason="no python3")
def test_real_interpreter_is_executable_class():
    result = triage_artifact(Path("/usr/bin/python3"), extract_strings_flag=False)
    assert result["ok"] is True
    assert result["security"]["arch"] in {"amd64", "x86", "aarch64", "arm"}


# ------------------------------------------------------- tool security boundary
#
# The production default is ATTRIBUTION_MODE=enforce (see app/config.py), so the
# tool is exercised the way the deployment runs it: every call carries a bound
# chat id, and calls without one are rejected before any filesystem access.

VALID_CHAT_ID = "ctf-triage-chat"


@pytest.fixture
def enforce_workspace(tmp_path, monkeypatch):
    """ATTRIBUTION_MODE=enforce with one bound chat (meta.json present)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    chat_root = tmp_path / "chats_storage"
    chat_dir = chat_root / VALID_CHAT_ID
    chat_dir.mkdir(parents=True)
    (chat_dir / "meta.json").write_text(
        f'{{"chat_id": "{VALID_CHAT_ID}", "created_at": "2026-08-26T00:00:00+00:00", '
        '"schema": 1, "next_seq": 1}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", workspace)
    monkeypatch.setattr(app.config, "HOST_RESTRICT_TO_WORKSPACE", True)
    # The host .env opts into Wave-1A scopes pointing at a real directory; the
    # tests must enforce the legacy boundary of the tmp workspace instead.
    monkeypatch.setattr(app.config, "HOST_READ_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_WRITE_SCOPE_SET", False)
    monkeypatch.setattr(app.config, "HOST_READ_DENY_GLOBS", [])
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", str(chat_root))
    return workspace


def test_tool_enforce_mode_requires_bound_chat(enforce_workspace):
    (enforce_workspace / "note.txt").write_text("hello\n")
    # No chat id and no bound context -> rejected before touching the file.
    result = ctf_triage_artifact("note.txt")
    assert result["ok"] is False
    assert result["error"]["code"] == "E6"


def test_tool_enforce_mode_rejects_invalid_chat_id(enforce_workspace):
    (enforce_workspace / "note.txt").write_text("hello\n")
    result = ctf_triage_artifact("note.txt", chat_id="../escape")
    assert result["ok"] is False
    assert "error" in result


def test_tool_traversal_is_policy_blocked(enforce_workspace):
    result = ctf_triage_artifact("../../etc/passwd", chat_id=VALID_CHAT_ID)
    assert result["ok"] is False
    assert result["error"]["code"] == "POLICY_BLOCKED"


def test_tool_outside_workspace_is_policy_blocked(enforce_workspace, tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 16)
    result = ctf_triage_artifact(str(outside), chat_id=VALID_CHAT_ID)
    assert result["ok"] is False
    assert result["error"]["code"] == "POLICY_BLOCKED"


def test_tool_missing_file_is_not_found(enforce_workspace):
    result = ctf_triage_artifact("does_not_exist.bin", chat_id=VALID_CHAT_ID)
    assert result["ok"] is False
    assert result["error"]["code"] == "FILE_NOT_FOUND"


def test_tool_directory_is_invalid_argument(enforce_workspace):
    result = ctf_triage_artifact(".", chat_id=VALID_CHAT_ID)
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_tool_reads_file_within_workspace(enforce_workspace):
    (enforce_workspace / "note.txt").write_text("hello triage\n")
    result = ctf_triage_artifact("note.txt", chat_id=VALID_CHAT_ID)
    assert result["ok"] is True
    assert result["filename"] == "note.txt"
    assert result["category"] in {"text", "unknown"}


# --------------------------------------------------------------------- harness


def _registered_tool(name: str):
    from app.mcp_server import mcp

    import app.main  # noqa: F401  (registers all tools)

    tools = asyncio.run(mcp.list_tools())
    return next((t for t in tools if t.name == name), None)


def test_harness_tool_description_directs_first_use():
    tool = _registered_tool("ctf_triage_artifact")
    assert tool is not None
    description = tool.description or ""
    assert "checksec" in description
    assert ("FIRST" in description or "BEFORE" in description)
    assert "readelf" in description or "checksec" in description


def test_harness_server_instructions_name_the_tool():
    import app.main  # noqa: F401
    from app.mcp_server import mcp

    instructions = mcp.instructions or ""
    assert "ctf_triage_artifact" in instructions
    assert "host_run_command" in instructions
    assert "ALWAYS" in instructions
