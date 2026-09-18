"""Authority records for one explicitly scoped CTF challenge case.

This module deliberately has no MCP dependency.  Its callers provide the
already-bound :class:`app.chat_workspace.WorkspaceManager`, which makes the
case record live beneath exactly that chat's workspace.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

from app import config
from app.chat_workspace import META_NAME, WORKSPACE_SCHEMA, WorkspaceManager, validate_chat_id


CASE_SCHEMA = 1
CASE_DIRECTORY_NAME = "ctf"
CASE_RECORD_NAME = "case.json"
ARTIFACT_DIRECTORY_NAME = "artifacts"
NETWORK_MODES = frozenset({"public_https", "local_instance"})
_CASE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}\Z")
_Resolve = Callable[..., list[tuple[Any, ...]]]
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


@dataclass(frozen=True)
class CaseRecord:
    """Immutable authority granted to one bound chat workspace."""

    case_id: str
    label: str
    authorized_origins: tuple[str, ...]
    network_mode: str
    created_at: str
    schema: int = CASE_SCHEMA

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["authorized_origins"] = list(self.authorized_origins)
        return data


@dataclass(frozen=True)
class CasePaths:
    """Resolved case storage paths, all contained by one chat workspace."""

    workspace: Path
    directory: Path
    record_file: Path
    artifact_dir: Path


def _bounded_int(name: str, default: int, ceiling: int) -> int:
    value = getattr(config, name, default)
    try:
        return min(ceiling, max(1, int(value)))
    except (TypeError, ValueError):
        return default


def _label_limit() -> int:
    return _bounded_int("CTF_CASE_MAX_LABEL_CHARS", 120, 120)


def _origin_limit() -> int:
    return _bounded_int("CTF_CASE_MAX_ORIGINS", 8, 8)


def _read_fd(fd: int, *, maximum: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(64 * 1024, maximum + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > maximum:
            raise ValueError("workspace metadata is too large.")
        chunks.append(chunk)


def _open_bound_workspace(manager: WorkspaceManager, chat_id: str) -> tuple[int, int, Path, str]:
    """Open the root and one bound workspace without following child links."""
    validated = validate_chat_id(chat_id)
    root = Path(manager.root).resolve(strict=False)
    try:
        root_fd = os.open(root, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        workspace_fd = os.open(
            validated, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=root_fd
        )
    except OSError as exc:
        try:
            os.close(root_fd)
        except UnboundLocalError:
            pass
        raise ValueError(f"chat workspace is not bound: {validated}") from exc
    try:
        meta_fd = os.open(META_NAME, os.O_RDONLY | _NOFOLLOW, dir_fd=workspace_fd)
        try:
            if not stat.S_ISREG(os.fstat(meta_fd).st_mode):
                raise ValueError("workspace metadata is invalid.")
            meta = json.loads(_read_fd(meta_fd, maximum=64 * 1024).decode("utf-8"))
        finally:
            os.close(meta_fd)
        if (
            not isinstance(meta, dict)
            or meta.get("chat_id") != validated
            or meta.get("schema") != WORKSPACE_SCHEMA
        ):
            raise ValueError("workspace metadata is invalid.")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        os.close(workspace_fd)
        os.close(root_fd)
        raise ValueError(f"chat workspace is not bound: {validated}") from exc
    return root_fd, workspace_fd, root / validated, validated


def _entry_matches(parent_fd: int, name: str, child_fd: int) -> bool:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    opened = os.fstat(child_fd)
    return stat.S_ISDIR(entry.st_mode) and (entry.st_dev, entry.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    )


def _open_private_directory(parent_fd: int, name: str, *, what: str) -> int:
    flags = os.O_RDONLY | _DIRECTORY | _NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ValueError(f"unable to create {what}.") from exc
    except OSError as exc:
        try:
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            entry = None
        if entry is not None and stat.S_ISLNK(entry.st_mode):
            raise ValueError(f"{what} escapes the chat workspace.") from exc
        raise ValueError(f"unable to open {what}.") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ValueError(f"{what} is not a directory.")
        os.fchmod(fd, 0o700)
        return fd
    except Exception:
        os.close(fd)
        raise


@contextmanager
def _open_case_storage(manager: WorkspaceManager, chat_id: str):
    """Yield descriptor-anchored private case storage for one bound chat."""
    root_fd, workspace_fd, workspace, validated = _open_bound_workspace(manager, chat_id)
    case_fd = artifact_fd = -1
    try:
        case_fd = _open_private_directory(
            workspace_fd, CASE_DIRECTORY_NAME, what="case directory"
        )
        artifact_fd = _open_private_directory(
            case_fd, ARTIFACT_DIRECTORY_NAME, what="artifact directory"
        )
        paths = CasePaths(
            workspace=workspace,
            directory=workspace / CASE_DIRECTORY_NAME,
            record_file=workspace / CASE_DIRECTORY_NAME / CASE_RECORD_NAME,
            artifact_dir=workspace / CASE_DIRECTORY_NAME / ARTIFACT_DIRECTORY_NAME,
        )
        yield paths, root_fd, workspace_fd, case_fd, artifact_fd, validated
    finally:
        for fd in (artifact_fd, case_fd, workspace_fd, root_fd):
            if fd >= 0:
                os.close(fd)


def _assert_case_storage_current(
    root_fd: int, workspace_fd: int, case_fd: int, artifact_fd: int, chat_id: str
) -> None:
    if not _entry_matches(root_fd, chat_id, workspace_fd):
        raise ValueError("chat workspace changed during case operation.")
    if not _entry_matches(workspace_fd, CASE_DIRECTORY_NAME, case_fd):
        raise ValueError("case directory changed during case operation.")
    if not _entry_matches(case_fd, ARTIFACT_DIRECTORY_NAME, artifact_fd):
        raise ValueError("artifact directory changed during case operation.")


def case_paths(manager: WorkspaceManager, chat_id: str) -> CasePaths:
    """Return the visible paths after safely establishing private storage."""
    with _open_case_storage(manager, chat_id) as storage:
        paths, root_fd, workspace_fd, case_fd, artifact_fd, validated = storage
        _assert_case_storage_current(
            root_fd, workspace_fd, case_fd, artifact_fd, validated
        )
        return paths


def _validate_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("label must be text.")
    label = value.strip()
    if not label:
        raise ValueError("label must not be blank.")
    if len(label) > _label_limit():
        raise ValueError(f"label must be at most {_label_limit()} characters.")
    if any(character in "\r\n\x00" for character in label):
        raise ValueError("label must be a single line of text.")
    return label


def _parsed_origin(value: str):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("origin must be a non-empty URL without whitespace.")
    if any(character.isspace() for character in value):
        raise ValueError("origin must not contain whitespace.")
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("origin must be an absolute URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("origins with embedded credentials are not supported.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("an authorized origin cannot include a path, query, or fragment.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin contains an invalid port.") from exc
    return parsed, port


def _canonical_host(hostname: str) -> tuple[str, ipaddress._BaseAddress | None]:
    if "%" in hostname:
        raise ValueError("IPv6 zone identifiers are not supported.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("origin hostname is invalid.") from exc
        if not host:
            raise ValueError("origin hostname is invalid.")
        return host, None
    return address.compressed, address


def _netloc(host: str, address: ipaddress._BaseAddress | None, port: int | None) -> str:
    shown_host = f"[{host}]" if address is not None and address.version == 6 else host
    return shown_host if port is None else f"{shown_host}:{port}"


def _resolved_addresses(host: str, port: int, resolver: _Resolve) -> set[ipaddress._BaseAddress]:
    try:
        results = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"unable to resolve origin host: {host}.") from exc
    addresses: set[ipaddress._BaseAddress] = set()
    for result in results:
        try:
            raw_address = result[4][0]
            addresses.add(ipaddress.ip_address(raw_address))
        except (IndexError, TypeError, ValueError):
            continue
    if not addresses:
        raise ValueError(f"origin host did not resolve to an IP address: {host}.")
    return addresses


def canonicalize_origin(
    value: str,
    network_mode: str,
    *,
    resolver: _Resolve = socket.getaddrinfo,
) -> str:
    """Normalize one origin while enforcing the mode's narrow authority."""
    if network_mode not in NETWORK_MODES:
        raise ValueError("network_mode must be 'public_https' or 'local_instance'.")
    parsed, port = _parsed_origin(value)
    scheme = parsed.scheme.lower()
    host, address = _canonical_host(parsed.hostname)

    if network_mode == "public_https":
        if scheme != "https":
            raise ValueError("public_https cases accept HTTPS origins only.")
        effective_port = 443 if port is None else port
        if not 1 <= effective_port <= 65535:
            raise ValueError("public_https origin port must be between 1 and 65535.")
        if address is None:
            addresses = _resolved_addresses(host, effective_port, resolver)
        else:
            addresses = {address}
        if any(not item.is_global for item in addresses):
            raise ValueError("public origin host must resolve only to global addresses.")
        return f"https://{_netloc(host, address, None if effective_port == 443 else effective_port)}"

    if scheme not in {"http", "https"}:
        raise ValueError("local_instance cases accept HTTP or HTTPS origins only.")
    if port is None or not 1 <= port <= 65535:
        raise ValueError("local_instance origins require an explicit port.")
    if host == "localhost":
        return f"{scheme}://localhost:{port}"
    if address is None or not address.is_loopback:
        raise ValueError("local_instance origins must use literal loopback or localhost.")
    return f"{scheme}://{_netloc(host, address, port)}"


def _normalize_origins(
    values: Iterable[str], network_mode: str, resolver: _Resolve
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("authorized_origins must be a list of origins.")
    try:
        supplied = list(values)
    except TypeError as exc:
        raise ValueError("authorized_origins must be a list of origins.") from exc
    limit = _origin_limit()
    if not 1 <= len(supplied) <= limit:
        raise ValueError(f"authorized_origins must contain between 1 and {limit} origins.")
    origins = tuple(canonicalize_origin(value, network_mode, resolver=resolver) for value in supplied)
    if len(set(origins)) != len(origins):
        raise ValueError("authorized_origins must not contain duplicate origins.")
    return origins


def _record_from_json(
    data: Mapping[str, Any], *, resolver: _Resolve = socket.getaddrinfo
) -> CaseRecord:
    try:
        case_id = data["case_id"]
        label = data["label"]
        origins = data["authorized_origins"]
        network_mode = data["network_mode"]
        created_at = data["created_at"]
        schema = data["schema"]
    except (KeyError, TypeError) as exc:
        raise ValueError("case record is malformed.") from exc
    if schema != CASE_SCHEMA or isinstance(schema, bool):
        raise ValueError("case record schema is unsupported.")
    if not isinstance(case_id, str) or _CASE_ID_PATTERN.fullmatch(case_id) is None:
        raise ValueError("case record id is malformed.")
    if not isinstance(created_at, str):
        raise ValueError("case record timestamp is malformed.")
    label = _validate_label(label)
    if network_mode not in NETWORK_MODES or not isinstance(origins, list):
        raise ValueError("case record authority is malformed.")
    # Stored origins must already be canonical. Public records are resolved
    # again here, and the request service will repeat that check before I/O.
    normalized = tuple(
        canonicalize_origin(origin, network_mode, resolver=resolver)
        for origin in origins
    )
    if list(normalized) != origins:
        raise ValueError("case record origins are not canonical.")
    if (
        not 1 <= len(normalized) <= _origin_limit()
        or len(set(normalized)) != len(normalized)
    ):
        raise ValueError("case record origins are malformed.")
    return CaseRecord(
        case_id=case_id,
        label=label,
        authorized_origins=normalized,
        network_mode=network_mode,
        created_at=created_at,
        schema=schema,
    )


def _atomic_write_json(directory_fd: int, name: str, data: Mapping[str, Any]) -> None:
    """Atomically replace one file through a held directory descriptor."""
    encoded = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = f".{name}.{secrets.token_hex(12)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except Exception:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except OSError:
            pass
        raise


def create_case(
    manager: WorkspaceManager,
    chat_id: str,
    *,
    label: str,
    authorized_origins: Iterable[str],
    network_mode: str,
    resolver: _Resolve = socket.getaddrinfo,
) -> CaseRecord:
    """Create or atomically replace the active CTF case for a bound chat."""
    normalized_label = _validate_label(label)
    origins = _normalize_origins(authorized_origins, network_mode, resolver)
    record = CaseRecord(
        case_id=secrets.token_urlsafe(18),
        label=normalized_label,
        authorized_origins=origins,
        network_mode=network_mode,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with _open_case_storage(manager, chat_id) as storage:
        _, root_fd, workspace_fd, case_fd, artifact_fd, validated = storage
        _atomic_write_json(case_fd, CASE_RECORD_NAME, record.to_json())
        _assert_case_storage_current(
            root_fd, workspace_fd, case_fd, artifact_fd, validated
        )
    return record


def load_active_case(
    manager: WorkspaceManager,
    chat_id: str,
    *,
    case_id: str | None = None,
    resolver: _Resolve = socket.getaddrinfo,
) -> CaseRecord:
    """Load the sole active case and optionally require its opaque id."""
    with _open_case_storage(manager, chat_id) as storage:
        _, root_fd, workspace_fd, case_fd, artifact_fd, validated = storage
        try:
            record_fd = os.open(
                CASE_RECORD_NAME, os.O_RDONLY | _NOFOLLOW, dir_fd=case_fd
            )
            try:
                if not stat.S_ISREG(os.fstat(record_fd).st_mode):
                    raise ValueError("active CTF case record is unreadable.")
                raw = _read_fd(record_fd, maximum=64 * 1024)
            finally:
                os.close(record_fd)
        except OSError as exc:
            raise ValueError("no active CTF case is configured for this chat.") from exc
        except ValueError:
            raise
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("active CTF case record is unreadable.") from exc
        _assert_case_storage_current(
            root_fd, workspace_fd, case_fd, artifact_fd, validated
        )
    record = _record_from_json(data, resolver=resolver)
    if case_id is not None:
        if not isinstance(case_id, str) or _CASE_ID_PATTERN.fullmatch(case_id) is None:
            raise ValueError("case_id is invalid.")
        if not hmac.compare_digest(record.case_id, case_id):
            raise ValueError("case_id does not match the active case.")
    return record
