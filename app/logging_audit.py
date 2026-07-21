from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from app.config import (
    AUDIT_LOG_BACKUP_COUNT,
    AUDIT_LOG_MAX_BYTES,
    AUDIT_MAX_FIELD_CHARS,
    LOG_FILE,
    SERVICE_NAME,
    VERSION,
)


logger = logging.getLogger("botquanganh_audit")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=AUDIT_LOG_MAX_BYTES,
            backupCount=AUDIT_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)
    except Exception as exc:  # pragma: no cover - environment-specific failure
        logger.warning("Audit file handler unavailable: %s", type(exc).__name__)


_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|authorization|cookie|password|passwd|secret|private[_-]?key|"
    r"api[_-]?key|gateway[_-]?token|session|access[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(token|password|passwd|secret|api[_-]?key|gateway[_-]?token|"
            r"access[_-]?key)=([^\s&;]+)"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        "[REDACTED API KEY]",
    ),
    (
        re.compile(
            r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED KEY MATERIAL]",
    ),
    (
        re.compile(r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]{20,}(?:\s+\S+)?"),
        "[REDACTED SSH KEY]",
    ),
)


def _redact_string(value: str) -> str:
    cleaned = value
    for pattern, replacement in _INLINE_SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    if len(cleaned) > AUDIT_MAX_FIELD_CHARS:
        cleaned = cleaned[:AUDIT_MAX_FIELD_CHARS] + "... [TRUNCATED]"
    return cleaned


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact secret keys and inline secret-shaped string values."""
    if isinstance(data, dict):
        redacted: dict[str, Any] = {}
        for raw_key, value in data.items():
            key = str(raw_key)
            if _SENSITIVE_KEY_RE.search(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(value)
        return redacted
    if isinstance(data, (list, tuple, set)):
        return [redact_sensitive_data(item) for item in data]
    if isinstance(data, str):
        return _redact_string(data)
    return data


def log_audit_event(event_type: str, details: Dict[str, Any] | None = None) -> None:
    """Write a versioned, redacted audit event to console and rotating JSONL log."""
    clean_details = redact_sensitive_data(details or {})
    payload = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": SERVICE_NAME,
        "service_version": VERSION,
        "event_type": _redact_string(str(event_type))[:200],
        "details": clean_details,
    }
    logger.info(
        "AUDIT_EVENT: %s",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def _audit_log_candidates() -> list[Path]:
    candidates = [LOG_FILE]
    candidates.extend(
        LOG_FILE.with_name(f"{LOG_FILE.name}.{index}")
        for index in range(1, AUDIT_LOG_BACKUP_COUNT + 1)
    )
    return [path for path in candidates if path.is_file()]


def get_audit_logs_for_run(run_id: str) -> str:
    """Retrieve matching events from the active and rotated audit logs."""
    normalized = str(run_id).strip()
    if not normalized or len(normalized) > 200 or "\n" in normalized or "\r" in normalized:
        raise ValueError("run_id must be a single non-empty line up to 200 characters")

    matching_lines: list[str] = []
    for path in _audit_log_candidates():
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if normalized in line:
                        matching_lines.append(line.rstrip("\n"))
        except OSError:
            continue
    return "\n".join(matching_lines)
