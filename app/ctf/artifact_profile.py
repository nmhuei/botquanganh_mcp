"""Passive, descriptor-anchored inspection of one scoped CTF artifact.

This service deliberately has no MCP dependency and never invokes a process,
extracts an archive, or mutates artifact content.  The public function accepts
only a direct filename in the active case's artifact directory.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from typing import Any

from app import config
from app.chat_workspace import WorkspaceManager
from app.ctf import case_scope


_CHUNK_SIZE = 64 * 1024
_MAGIC_BYTES = 512
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _bounded_config(name: str, fallback: int, ceiling: int) -> int:
    """Read a safety cap defensively, including during configuration tests."""
    try:
        return min(ceiling, max(1, int(getattr(config, name, fallback))))
    except (TypeError, ValueError):
        return fallback


def _artifact_name(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("artifact name must be a non-empty filename.")
    if "\x00" in value or value in {".", ".."}:
        raise ValueError("artifact name is invalid.")
    if "/" in value or "\\" in value or Path(value).is_absolute():
        raise ValueError("artifact path must name one file in the artifact directory.")
    return value


def _pread(fd: int, offset: int, maximum: int) -> bytes:
    """Read at most *maximum* bytes without changing the descriptor position."""
    if maximum <= 0:
        return b""
    chunks: list[bytes] = []
    remaining = maximum
    position = offset
    while remaining:
        chunk = os.pread(fd, min(_CHUNK_SIZE, remaining), position)
        if not chunk:
            break
        chunks.append(chunk)
        position += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _magic(head: bytes, name: str) -> str:
    if head.startswith(b"\x7fELF"):
        return "ELF"
    if head.startswith(b"MZ"):
        return "PE"
    if head[:4] in {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    }:
        return "Mach-O"
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "APK" if name.lower().endswith(".apk") else "ZIP"
    if head.startswith(b"\x1f\x8b"):
        return "GZIP"
    if head.startswith(b"%PDF-"):
        return "PDF"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head[:4] in {b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"M<\xb2\xa1", b"\xa1\xb2<M"}:
        return "PCAP"
    if head.startswith(b"\x0a\x0d\x0d\x0a"):
        return "PCAPNG"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "WAV"
    if head.startswith(b"SQLite format 3\x00"):
        return "SQLite"
    if head.startswith(b"\x00asm"):
        return "WASM"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "TAR"
    return "unknown"


def _hash(fd: int, size: int) -> dict[str, Any]:
    limit = _bounded_config("CTF_ARTIFACT_HASH_MAX_BYTES", 4 * 1024 * 1024, 16 * 1024 * 1024)
    if size <= limit:
        digest, hashed = _hash_ranges(fd, ((0, size),))
        return {"mode": "full", "bytes_hashed": hashed, "value": digest}

    prefix_size = limit // 2
    suffix_size = limit - prefix_size
    digest, hashed = _hash_ranges(
        fd, ((0, prefix_size), (size - suffix_size, suffix_size))
    )
    return {
        "mode": "sampled_prefix_suffix",
        "bytes_hashed": hashed,
        "value": digest,
    }


def _hash_ranges(fd: int, ranges: tuple[tuple[int, int], ...]) -> tuple[str, int]:
    """Hash fixed byte ranges in chunks, rejecting short reads coherently."""
    hasher = hashlib.sha256()
    hashed = 0
    for offset, length in ranges:
        position = offset
        remaining = length
        while remaining:
            chunk = os.pread(fd, min(_CHUNK_SIZE, remaining), position)
            if not chunk:
                raise ValueError("artifact changed while it was being profiled.")
            hasher.update(chunk)
            position += len(chunk)
            remaining -= len(chunk)
            hashed += len(chunk)
    return hasher.hexdigest(), hashed


def _entropy(fd: int, size: int) -> dict[str, Any]:
    limit = _bounded_config("CTF_ARTIFACT_ENTROPY_MAX_BYTES", 256 * 1024, 2 * 1024 * 1024)
    data = _pread(fd, 0, min(size, limit))
    if not data:
        bits = 0.0
    else:
        total = len(data)
        bits = -sum(
            (count / total) * math.log2(count / total) for count in Counter(data).values()
        )
    return {
        "bits_per_byte": round(bits, 6),
        "bytes_sampled": len(data),
        "sampled": size > len(data),
    }


def _unavailable_manifest(format_name: str, reason: str) -> dict[str, Any]:
    return {
        "format": format_name,
        "inspection": "unavailable",
        "reason": reason,
        "members": [],
        "members_truncated": False,
    }


def _stat_snapshot(item: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return all metadata needed to reject an in-place artifact change."""
    return (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _zip_manifest(fd: int, size: int) -> dict[str, Any]:
    metadata_limit = _bounded_config(
        "CTF_ARTIFACT_ARCHIVE_METADATA_MAX_BYTES", 1024 * 1024, 4 * 1024 * 1024
    )
    tail_size = min(size, 65_557)
    tail = _pread(fd, size - tail_size, tail_size)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or marker + 22 > len(tail):
        return _unavailable_manifest("ZIP", "ZIP end-of-central-directory record is unavailable.")
    fields = struct.unpack_from("<4s4H2LH", tail, marker)
    _, disk, directory_disk, disk_entries, entries, directory_size, directory_offset, comment_size = fields
    if marker + 22 + comment_size != len(tail):
        return _unavailable_manifest("ZIP", "ZIP end-of-central-directory record is malformed.")
    if disk or directory_disk or disk_entries != entries:
        return _unavailable_manifest("ZIP", "multi-disk ZIP manifests are not inspected.")
    if entries == 0xFFFF or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        return _unavailable_manifest("ZIP", "ZIP64 manifests are not inspected.")
    if directory_size > metadata_limit:
        return _unavailable_manifest("ZIP", "ZIP metadata exceeds the inspection limit.")
    if directory_offset + directory_size > size:
        return _unavailable_manifest("ZIP", "ZIP central directory is outside the artifact.")
    directory = _pread(fd, directory_offset, directory_size)
    if len(directory) != directory_size:
        return _unavailable_manifest("ZIP", "artifact changed while reading ZIP metadata.")

    listed_limit = _bounded_config("CTF_ARTIFACT_MAX_MANIFEST_MEMBERS", 64, 256)
    members: list[str] = []
    total_member_bytes = 0
    position = 0
    for _ in range(entries):
        if position + 46 > len(directory) or directory[position : position + 4] != b"PK\x01\x02":
            return _unavailable_manifest("ZIP", "ZIP central directory is malformed.")
        header = struct.unpack_from("<4s6H3L5H2L", directory, position)
        flags, member_size, name_size, extra_size, comment_size = (
            header[3],
            header[9],
            header[10],
            header[11],
            header[12],
        )
        end = position + 46 + name_size + extra_size + comment_size
        if end > len(directory):
            return _unavailable_manifest("ZIP", "ZIP member metadata is malformed.")
        if len(members) < listed_limit:
            raw_name = directory[position + 46 : position + 46 + name_size]
            encoding = "utf-8" if flags & 0x800 else "cp437"
            members.append(raw_name.decode(encoding, errors="replace"))
        total_member_bytes += member_size
        position = end
    return {
        "format": "ZIP",
        "inspection": "metadata_only",
        "member_count": entries,
        "member_count_complete": True,
        "members": members,
        "members_truncated": entries > len(members),
        "uncompressed_member_bytes": total_member_bytes,
    }


def _tar_size(raw: bytes) -> int | None:
    value = raw.rstrip(b"\x00 ").lstrip(b" ")
    if not value:
        return 0
    if value[0] & 0x80:
        return None  # GNU base-256 sizes are intentionally not parsed here.
    try:
        return int(value, 8)
    except ValueError:
        return None


def _tar_manifest(fd: int, size: int) -> dict[str, Any]:
    listed_limit = _bounded_config("CTF_ARTIFACT_MAX_MANIFEST_MEMBERS", 64, 256)
    header_limit = _bounded_config("CTF_ARTIFACT_TAR_MAX_HEADERS", 512, 2048)
    members: list[str] = []
    member_count = total_member_bytes = 0
    offset = 0
    for _ in range(header_limit):
        header = _pread(fd, offset, 512)
        if len(header) != 512:
            return _unavailable_manifest("TAR", "TAR header is truncated.")
        if header == b"\x00" * 512:
            terminator = _pread(fd, offset + 512, 512)
            if terminator != b"\x00" * 512:
                return _unavailable_manifest("TAR", "TAR terminator is incomplete.")
            return {
                "format": "TAR",
                "inspection": "metadata_only",
                "member_count": member_count,
                "member_count_complete": True,
                "members": members,
                "members_truncated": member_count > len(members),
                "uncompressed_member_bytes": total_member_bytes,
            }
        member_size = _tar_size(header[124:136])
        if member_size is None:
            return _unavailable_manifest("TAR", "TAR member size is unsupported.")
        raw_name = header[:100].split(b"\x00", 1)[0]
        raw_prefix = header[345:500].split(b"\x00", 1)[0]
        name = b"/".join(part for part in (raw_prefix, raw_name) if part).decode(
            "utf-8", errors="replace"
        )
        member_count += 1
        total_member_bytes += member_size
        if len(members) < listed_limit:
            members.append(name)
        next_offset = offset + 512 + ((member_size + 511) // 512) * 512
        if next_offset > size:
            return _unavailable_manifest("TAR", "TAR member extends beyond the artifact.")
        offset = next_offset
    return {
        "format": "TAR",
        "inspection": "metadata_only",
        "member_count": member_count,
        "member_count_complete": False,
        "members": members,
        "members_truncated": member_count > len(members),
        "uncompressed_member_bytes": total_member_bytes,
        "reason": "TAR header inspection limit reached.",
    }


def _archive_manifest(fd: int, size: int, format_name: str) -> dict[str, Any] | None:
    if format_name in {"ZIP", "APK"}:
        return _zip_manifest(fd, size)
    if format_name == "TAR":
        return _tar_manifest(fd, size)
    return None


def _next_safe_actions(format_name: str) -> list[str]:
    actions = ["Use ctf_transform only on explicit caller-supplied bytes or text."]
    if format_name in {"ZIP", "APK", "TAR"}:
        actions.insert(0, "Review the bounded archive manifest; do not extract unknown members automatically.")
    elif format_name == "GZIP":
        actions.insert(0, "Treat GZIP as opaque; do not decompress it automatically.")
    else:
        actions.insert(0, "Add a separate artifact for any further offline inspection.")
    return actions


def _profile_open_artifact(fd: int, size: int, artifact_name: str) -> dict[str, Any]:
    head = _pread(fd, 0, min(size, _MAGIC_BYTES))
    format_name = _magic(head, artifact_name)
    digest = _hash(fd, size)
    entropy = _entropy(fd, size)
    manifest = _archive_manifest(fd, size, format_name)
    result: dict[str, Any] = {
        "relative_path": f"ctf/artifacts/{artifact_name}",
        "size_bytes": size,
        "magic": {"format": format_name, "bytes_examined": len(head)},
        "sha256": digest,
        "entropy": entropy,
        "evidence": [
            {"kind": "path", "value": f"ctf/artifacts/{artifact_name}"},
            {"kind": "size_bytes", "value": size},
            {"kind": "magic", "value": format_name},
            {"kind": "sha256", "mode": digest["mode"], "bytes_hashed": digest["bytes_hashed"]},
            {"kind": "entropy", "bytes_sampled": entropy["bytes_sampled"]},
        ],
        "next_safe_actions": _next_safe_actions(format_name),
    }
    if manifest is not None:
        result["archive_manifest"] = manifest
    return result


def profile_artifact(
    manager: WorkspaceManager, chat_id: str, artifact_name: str
) -> dict[str, Any]:
    """Return bounded, read-only evidence for one active-case artifact.

    The lookup is anchored to the artifact directory descriptor held by
    :mod:`case_scope`, so traversal and replacement cannot redirect reads
    outside the invoking chat workspace.
    """
    name = _artifact_name(artifact_name)
    case_scope.load_active_case(manager, chat_id)
    with case_scope._open_case_storage(manager, chat_id) as storage:
        _, root_fd, workspace_fd, case_fd, artifact_fd, validated = storage
        case_scope._assert_case_storage_current(
            root_fd, workspace_fd, case_fd, artifact_fd, validated
        )
        try:
            entry = os.stat(name, dir_fd=artifact_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ValueError("artifact was not found in the active artifact directory.") from exc
        if stat.S_ISLNK(entry.st_mode):
            raise ValueError("artifact symlink is not permitted.")
        if not stat.S_ISREG(entry.st_mode):
            raise ValueError("artifact must be a regular file.")
        try:
            fd = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=artifact_fd)
        except OSError as exc:
            raise ValueError("artifact cannot be opened safely.") from exc
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError("artifact must be a regular file.")
            if (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("artifact changed during safe open.")
            opened_snapshot = _stat_snapshot(opened)
            case_scope._assert_case_storage_current(
                root_fd, workspace_fd, case_fd, artifact_fd, validated
            )
            result = _profile_open_artifact(fd, opened.st_size, name)
            if _stat_snapshot(os.fstat(fd)) != opened_snapshot:
                raise ValueError("artifact changed while it was being profiled.")
            try:
                current_entry = os.stat(name, dir_fd=artifact_fd, follow_symlinks=False)
            except OSError as exc:
                raise ValueError("artifact changed while it was being profiled.") from exc
            if not stat.S_ISREG(current_entry.st_mode) or (
                current_entry.st_dev,
                current_entry.st_ino,
            ) != (opened.st_dev, opened.st_ino):
                raise ValueError("artifact changed while it was being profiled.")
            return result
        finally:
            os.close(fd)
