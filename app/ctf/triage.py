"""Static artifact triage engine for CTF challenges.

Performs pure-Python inspection without spawning external processes:
- Magic bytes & format classification
- Comprehensive ELF parsing (architecture, endianness, NX, PIE, Canary, RELRO, Stripped)
- PE (Windows) binary header inspection (machine, ASLR/DEP)
- Shannon entropy calculation
- Bounded extraction of suspicious strings (flags, URLs, commands, format strings)
"""

from __future__ import annotations

import binascii
import math
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

# Maximum bytes to inspect for strings and entropy sampling
MAX_SAMPLE_BYTES = 2 * 1024 * 1024  # 2MB

# Patterns of interest for CTF string triage
_SUSPICIOUS_REGEXES = [
    re.compile(rb"(?i)(?:flag|ctf|picoctf|securinets|svattt)\{[^\s}\"']{4,120}\}"),
    re.compile(rb"(?:https?|ftp|tcp|udp)://[^\s\"']{4,80}"),
    re.compile(rb"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::[0-9]{1,5})?\b"),
    re.compile(rb"(?:/bin/(?:ba)?sh|/usr/bin/(?:ba)?sh|cmd\.exe|powershell)"),
    re.compile(rb"(?:/etc/passwd|/etc/shadow|/flag(?:\.txt)?|flag\.txt)"),
    re.compile(rb"%[0-9]*[sdpxn]"),
    re.compile(rb"\b(?:system|execve|popen|mprotect|mmap|VirtualAlloc|WinExec)\b"),
]

# Magic byte signatures: (magic_bytes, offset, format_name, category)
_MAGIC_SIGNATURES: tuple[tuple[bytes, int, str, str], ...] = (
    (b"\x7fELF", 0, "ELF Executable / Library", "executable"),
    (b"MZ", 0, "PE Executable (Windows DOS/PE)", "executable"),
    (b"\xca\xfe\xba\xbe", 0, "Java Class / Mach-O Fat Binary", "executable"),
    (b"\xfe\xed\xfa\xce", 0, "Mach-O 32-bit (Big Endian)", "executable"),
    (b"\xfe\xed\xfa\xcf", 0, "Mach-O 64-bit (Big Endian)", "executable"),
    (b"\xce\xfa\xed\xfe", 0, "Mach-O 32-bit (Little Endian)", "executable"),
    (b"\xcf\xfa\xed\xfe", 0, "Mach-O 64-bit (Little Endian)", "executable"),
    (b"\x00asm", 0, "WebAssembly Binary (WASM)", "executable"),
    (b"dex\n035\x00", 0, "Android Dalvik Executable (DEX)", "executable"),
    (b"dex\n037\x00", 0, "Android Dalvik Executable (DEX)", "executable"),
    (b"dex\n038\x00", 0, "Android Dalvik Executable (DEX)", "executable"),
    (b"dex\n039\x00", 0, "Android Dalvik Executable (DEX)", "executable"),
    (b"PK\x03\x04", 0, "ZIP Archive (ZIP/APK/JAR/DOCX)", "archive"),
    (b"7z\xbc\xaf\x27\x1c", 0, "7-Zip Archive", "archive"),
    (b"Rar!\x1a\x07\x00", 0, "RAR Archive (v4)", "archive"),
    (b"Rar!\x1a\x07\x01\x00", 0, "RAR Archive (v5)", "archive"),
    (b"\x1f\x8b", 0, "Gzip Compressed Data", "archive"),
    (b"BZh", 0, "Bzip2 Compressed Data", "archive"),
    (b"\xfd7zXZ\x00", 0, "XZ Compressed Data", "archive"),
    (b"\x89PNG\r\n\x1a\n", 0, "PNG Image", "media"),
    (b"\xff\xd8\xff", 0, "JPEG Image", "media"),
    (b"GIF87a", 0, "GIF87a Image", "media"),
    (b"GIF89a", 0, "GIF89a Image", "media"),
    (b"BM", 0, "BMP Image", "media"),
    (b"RIFF", 0, "RIFF Container (WAV/AVI/WEBP)", "media"),
    (b"%PDF-", 0, "PDF Document", "document"),
    (b"SQLite format 3\x00", 0, "SQLite 3 Database", "database"),
    (b"\xd4\xc3\xb2\xa1", 0, "PCAP Capture (Little Endian)", "network"),
    (b"\xa1\xb2\xc3\xd4", 0, "PCAP Capture (Big Endian)", "network"),
    (b"\x0a\x0d\x0d\x0a", 0, "PCAPNG Capture", "network"),
)

_ELF_MACHINES = {
    0x02: "SPARC",
    0x03: "x86",
    0x08: "MIPS",
    0x14: "PowerPC",
    0x28: "ARM (32-bit)",
    0x3E: "amd64 (x86-64)",
    0xB7: "AArch64 (ARM 64-bit)",
    0xF3: "RISC-V",
}

_ELF_ARCH_ID = {
    0x02: "sparc",
    0x03: "x86",
    0x08: "mips",
    0x14: "ppc",
    0x28: "arm",
    0x3E: "amd64",
    0xB7: "aarch64",
    0xF3: "riscv",
}

_ELF_ARCH_DISPLAY = {
    0x02: "SPARC",
    0x03: "x86",
    0x08: "MIPS",
    0x14: "PowerPC",
    0x28: "ARM",
    0x3E: "x86-64",
    0xB7: "AArch64",
    0xF3: "RISC-V",
}

_ELF_TYPES = {
    1: "ET_REL (Relocatable object file)",
    2: "ET_EXEC (Executable file)",
    3: "ET_DYN (Position-Independent Executable / Shared Object)",
    4: "ET_CORE (Core dump)",
}


def calculate_entropy(data: bytes) -> dict[str, Any]:
    """Calculate Shannon Entropy (0.0 to 8.0) of a byte stream."""
    if not data:
        return {"score": 0.0, "assessment": "empty_file"}

    counts = Counter(data)
    total = len(data)
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)

    rounded = round(entropy, 3)
    if rounded < 6.0:
        assessment = "normal_text"
    elif rounded <= 7.2:
        assessment = "normal_binary"
    else:
        assessment = "packed_or_encrypted"

    return {
        "score": rounded,
        "assessment": assessment,
        "sample_bytes": total,
    }


def detect_magic(header: bytes, file_size: int) -> dict[str, Any]:
    """Identify file category and MIME signature from raw header bytes."""
    if not header:
        return {
            "format": "Empty File",
            "category": "empty",
            "magic_hex": "",
        }

    for magic, offset, name, cat in _MAGIC_SIGNATURES:
        if len(header) >= offset + len(magic) and header[offset : offset + len(magic)] == magic:
            return {
                "format": name,
                "category": cat,
                "magic_hex": binascii.hexlify(magic).decode("ascii"),
            }

    # Tar check: "ustar" at offset 257
    if len(header) >= 262 and header[257:262] == b"ustar":
        return {
            "format": "POSIX Tar Archive",
            "category": "archive",
            "magic_hex": binascii.hexlify(b"ustar").decode("ascii"),
        }

    # Check for printable text
    printable_chars = sum(1 for b in header[:1024] if 32 <= b <= 126 or b in (9, 10, 13))
    ratio = printable_chars / min(len(header), 1024)
    if ratio > 0.85:
        return {
            "format": "Plain Text (ASCII/UTF-8)",
            "category": "text",
            "magic_hex": binascii.hexlify(header[:8]).decode("ascii"),
        }

    return {
        "format": "Unknown Raw Binary Data",
        "category": "unknown",
        "magic_hex": binascii.hexlify(header[:8]).decode("ascii"),
    }


def parse_elf(data: bytes) -> dict[str, Any] | None:
    """Parse ELF binary headers to extract architecture, endianness, and security flags."""
    if len(data) < 52 or data[:4] != b"\x7fELF":
        return None

    ei_class = data[4]  # 1 = 32-bit, 2 = 64-bit
    ei_data = data[5]   # 1 = Little Endian, 2 = Big Endian

    if ei_class not in (1, 2) or ei_data not in (1, 2):
        return None

    endian = "<" if ei_data == 1 else ">"
    is_64 = ei_class == 2

    try:
        if is_64:
            if len(data) < 64:
                return None
            (
                e_type,
                e_machine,
                e_version,
                e_entry,
                e_phoff,
                e_shoff,
                e_flags,
                e_ehsize,
                e_phentsize,
                e_phnum,
                e_shentsize,
                e_shnum,
                e_shstrndx,
            ) = struct.unpack(endian + "HHIQQQIHHHHHH", data[16:64])
        else:
            (
                e_type,
                e_machine,
                e_version,
                e_entry,
                e_phoff,
                e_shoff,
                e_flags,
                e_ehsize,
                e_phentsize,
                e_phnum,
                e_shentsize,
                e_shnum,
                e_shstrndx,
            ) = struct.unpack(endian + "HHIIIIIHHHHHH", data[16:52])
    except struct.error:
        return None

    arch_name = _ELF_MACHINES.get(e_machine, f"Unknown ({hex(e_machine)})")
    type_name = _ELF_TYPES.get(e_type, f"Unknown ({e_type})")

    # Program Headers inspection
    nx = False
    has_gnu_stack = False
    has_relro = False
    dynamic_offset: int | None = None
    dynamic_size: int | None = None

    if e_phoff and e_phnum and e_phentsize:
        for i in range(min(e_phnum, 128)):
            off = e_phoff + i * e_phentsize
            if off + e_phentsize > len(data):
                break
            try:
                if is_64:
                    p_type, p_flags, p_offset, _, _, p_filesz, _, _ = struct.unpack(
                        endian + "IIQQQQQQ", data[off : off + 56]
                    )
                else:
                    p_type, p_offset, _, _, p_filesz, _, p_flags, _ = struct.unpack(
                        endian + "IIIIIIII", data[off : off + 32]
                    )
            except struct.error:
                break

            if p_type == 0x6474E551:  # PT_GNU_STACK
                has_gnu_stack = True
                nx = (p_flags & 1) == 0  # PF_X is 1 -> executable stack
            elif p_type == 0x6474E552:  # PT_GNU_RELRO
                has_relro = True
            elif p_type == 2:  # PT_DYNAMIC
                dynamic_offset = p_offset
                dynamic_size = p_filesz

    # Dynamic section inspection for RELRO (BIND_NOW) and PIE (DF_1_PIE)
    bind_now = False
    df1_pie = False
    if dynamic_offset and dynamic_size:
        dyn_entry_size = 16 if is_64 else 8
        num_dyn = min(dynamic_size // dyn_entry_size, 512)
        for d_i in range(num_dyn):
            d_off = dynamic_offset + d_i * dyn_entry_size
            if d_off + dyn_entry_size > len(data):
                break
            try:
                if is_64:
                    d_tag, d_val = struct.unpack(endian + "qQ", data[d_off : d_off + 16])
                else:
                    d_tag, d_val = struct.unpack(endian + "iI", data[d_off : d_off + 8])
            except struct.error:
                break

            if d_tag == 0:  # DT_NULL
                break
            if d_tag == 24:  # DT_BIND_NOW
                bind_now = True
            elif d_tag == 30 and (d_val & 0x8):  # DT_FLAGS with DF_BIND_NOW
                bind_now = True
            elif d_tag == 0x6FFFFFFB:  # DT_FLAGS_1
                if d_val & 0x1:  # DF_1_NOW
                    bind_now = True
                if d_val & 0x08000000:  # DF_1_PIE (bit 27)
                    df1_pie = True

    if has_relro:
        relro = "Full RELRO" if bind_now else "Partial RELRO"
    else:
        relro = "No RELRO"

    # PIE: ET_EXEC -> No PIE; ET_DYN -> check DF_1_PIE (distinguishes PIE from shared lib)
    if e_type == 2:  # ET_EXEC
        pie = False
    elif e_type == 3:  # ET_DYN
        pie = df1_pie
    else:
        pie = False

    # file(1)-style kind for the rich format string
    if e_type == 2:
        kind = "executable"
    elif e_type == 3:
        kind = "pie executable" if df1_pie else "shared object"
    elif e_type == 1:
        kind = "relocatable"
    elif e_type == 4:
        kind = "core file"
    else:
        kind = "unknown"

    # Section Headers inspection (stripped status) + Stack Canary via string tables
    stripped = True
    canary = False
    section_names: list[str] = []
    if e_shoff and e_shnum and e_shentsize and e_shstrndx < e_shnum:
        shdr_size = 64 if is_64 else 40
        shdr_fmt = endian + ("IIQQQQIIQQ" if is_64 else "IIIIIIIIII")
        try:
            shstr_off = e_shoff + e_shstrndx * e_shentsize
            if shstr_off + shdr_size <= len(data):
                shstr_hdr = struct.unpack(shdr_fmt, data[shstr_off : shstr_off + shdr_size])
                str_offset, str_size = shstr_hdr[4], shstr_hdr[5]
                if str_offset + str_size <= len(data):
                    shstrtab = data[str_offset : str_offset + str_size]
                    for s_i in range(min(e_shnum, 256)):
                        s_off = e_shoff + s_i * e_shentsize
                        if s_off + shdr_size > len(data):
                            break
                        shdr = struct.unpack(shdr_fmt, data[s_off : s_off + shdr_size])
                        sh_name_idx, sh_offset, sh_size = shdr[0], shdr[4], shdr[5]
                        name_end = shstrtab.find(b"\x00", sh_name_idx)
                        name = ""
                        if name_end != -1:
                            name = shstrtab[sh_name_idx:name_end].decode("ascii", errors="replace")
                        if name:
                            section_names.append(name)
                            if name == ".symtab":
                                stripped = False
                        # Canary: __stack_chk_fail symbol present in .dynstr / .strtab
                        if name in (".strtab", ".dynstr") and sh_offset + sh_size <= len(data):
                            if b"__stack_chk_fail" in data[sh_offset : sh_offset + sh_size]:
                                canary = True
        except Exception:
            pass

    return {
        "class": "64-bit" if is_64 else "32-bit",
        "endian": "little" if ei_data == 1 else "big",
        "arch": arch_name,
        "arch_id": _ELF_ARCH_ID.get(e_machine, f"unknown({hex(e_machine)})"),
        "arch_display": _ELF_ARCH_DISPLAY.get(e_machine, f"unknown({hex(e_machine)})"),
        "type": e_type,
        "type_name": type_name,
        "kind": kind,
        "entry_point": hex(e_entry),
        "checksec": {
            "nx": nx,
            "pie": pie,
            "canary": canary,
            "relro": relro,
            "stripped": stripped,
        },
        "sections": section_names[:25],
    }


def parse_pe(data: bytes) -> dict[str, Any] | None:
    """Parse PE (Windows portable executable) headers for basic mitigations."""
    if len(data) < 64 or data[:2] != b"MZ":
        return None

    e_lfanew = struct.unpack("<I", data[0x3C:0x40])[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return None

    try:
        machine, num_sections, _, _, _, opt_hdr_size, characteristics = struct.unpack(
            "<HHIIIHH", data[e_lfanew + 4 : e_lfanew + 24]
        )
    except struct.error:
        return None

    arch = {
        0x014C: "x86 (32-bit)",
        0x8664: "x64 (AMD64)",
        0xAA64: "ARM64",
    }.get(machine, f"Unknown ({hex(machine)})")

    aslr = False
    dep = False
    cfg = False

    # Check Optional Header for DllCharacteristics
    opt_offset = e_lfanew + 24
    if opt_hdr_size >= 72 and opt_offset + opt_hdr_size <= len(data):
        magic = struct.unpack("<H", data[opt_offset : opt_offset + 2])[0]
        # PE32 (0x10b) DllCharacteristics is at offset 70; PE32+ (0x20b) is at offset 70
        if opt_offset + 72 <= len(data):
            dll_chars = struct.unpack("<H", data[opt_offset + 70 : opt_offset + 72])[0]
            aslr = bool(dll_chars & 0x0040)  # IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE
            dep = bool(dll_chars & 0x0100)   # IMAGE_DLLCHARACTERISTICS_NX_COMPAT
            cfg = bool(dll_chars & 0x4000)   # IMAGE_DLLCHARACTERISTICS_GUARD_CF

    return {
        "format": "PE32+" if opt_hdr_size > 0 and data[opt_offset:opt_offset+2] == b"\x0b\x02" else "PE32",
        "arch": arch,
        "is_dll": bool(characteristics & 0x2000),
        "checksec": {
            "aslr": aslr,
            "dep_nx": dep,
            "cfg": cfg,
        },
    }


def extract_suspicious_strings(
    data: bytes, min_len: int = 6, max_count: int = 35
) -> list[str]:
    """Scan and return prioritized strings matching CTF patterns and indicators."""
    if not data:
        return []

    sample = data[:MAX_SAMPLE_BYTES]
    results: list[str] = []
    seen: set[str] = set()

    for pattern in _SUSPICIOUS_REGEXES:
        for match in pattern.finditer(sample):
            text = match.group(0).decode("utf-8", errors="replace").strip()
            if text and text not in seen:
                seen.add(text)
                results.append(text)
                if len(results) >= max_count:
                    return results

    # General ASCII strings collection if we have remaining capacity
    raw_strings = re.findall(rb"[\x20-\x7e]{" + str(min_len).encode("ascii") + rb",}", sample)
    for raw in raw_strings:
        if len(results) >= max_count:
            break
        text = raw.decode("ascii", errors="replace").strip()
        # Keep strings that have interesting characters or paths
        if text not in seen and any(c in text for c in ("/", ".", ":", "%", "_", "-")):
            seen.add(text)
            results.append(text)

    return results


def triage_artifact(
    file_path: Path,
    *,
    calculate_entropy_flag: bool = True,
    extract_strings_flag: bool = True,
    strings_min_len: int = 6,
) -> dict[str, Any]:
    """Perform comprehensive static triage on an artifact file."""
    if not file_path.exists():
        return {"ok": False, "error": f"File not found: {file_path}"}
    if not file_path.is_file():
        return {"ok": False, "error": f"Not a regular file: {file_path}"}

    file_size = file_path.stat().st_size
    with file_path.open("rb") as handle:
        header = handle.read(4096)
        if file_size <= MAX_SAMPLE_BYTES:
            handle.seek(0)
            full_or_sample = handle.read()
        else:
            handle.seek(0)
            full_or_sample = handle.read(MAX_SAMPLE_BYTES)

    magic_info = detect_magic(header, file_size)

    elf_info: dict[str, Any] | None = None
    pe_info: dict[str, Any] | None = None

    if header.startswith(b"\x7fELF"):
        elf_info = parse_elf(full_or_sample)
    elif header.startswith(b"MZ"):
        pe_info = parse_pe(full_or_sample)

    entropy_info = calculate_entropy(full_or_sample) if calculate_entropy_flag else None
    strings_preview = (
        extract_suspicious_strings(full_or_sample, min_len=strings_min_len)
        if extract_strings_flag
        else []
    )

    result: dict[str, Any] = {
        "ok": True,
        "filename": file_path.name,
        "size_bytes": file_size,
        "category": magic_info["category"],
        "magic_hex": magic_info["magic_hex"],
    }

    if elf_info:
        result["format"] = (
            f"ELF {elf_info['class']} "
            f"{'LSB' if elf_info['endian'] == 'little' else 'MSB'} "
            f"{elf_info['kind']}, {elf_info['arch_display']}"
        )
        relro_short = {
            "Full RELRO": "Full",
            "Partial RELRO": "Partial",
            "No RELRO": "No",
        }.get(elf_info["checksec"]["relro"], elf_info["checksec"]["relro"])
        result["security"] = {
            "arch": elf_info["arch_id"],
            "endian": elf_info["endian"],
            "nx": elf_info["checksec"]["nx"],
            "pie": elf_info["checksec"]["pie"],
            "canary": elf_info["checksec"]["canary"],
            "relro": relro_short,
            "stripped": elf_info["checksec"]["stripped"],
        }
        result["elf"] = elf_info
    elif pe_info:
        result["format"] = magic_info["format"]
        result["pe"] = pe_info
        result["security"] = {
            "arch": pe_info["arch"],
            "aslr": pe_info["checksec"]["aslr"],
            "dep_nx": pe_info["checksec"]["dep_nx"],
            "cfg": pe_info["checksec"]["cfg"],
        }
    else:
        result["format"] = magic_info["format"]

    if entropy_info:
        result["entropy"] = entropy_info

    if strings_preview:
        result["suspicious_strings"] = strings_preview

    return result
