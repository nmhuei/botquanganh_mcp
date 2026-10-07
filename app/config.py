import codecs
import math
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal .env loading.
#
# Mirrors `dotenv.load_dotenv()` defaults (override=False, interpolate=True,
# encoding="utf-8", discovery = nearest `.env` walking up from this file) so
# the CLI does not pay the ~19ms python-dotenv import on every invocation.
# Parity is enforced by tests/test_config_env_parity.py; if that suite fails,
# this loader must be fixed or reverted to python-dotenv.
# ---------------------------------------------------------------------------

_HWS = r"[^\S\r\n]"  # horizontal whitespace
_ENV_WS_ALL = re.compile(r"\s*")
_ENV_EXPORT = re.compile(rf"(?:export{_HWS}+)?")
_ENV_KEY_Q = re.compile(r"'([^']+)'")
_ENV_KEY_UQ = re.compile(r"([^=#\s]+)")
_ENV_HWS = re.compile(rf"{_HWS}*")
_ENV_EQ = re.compile(rf"(={_HWS}*)")
_ENV_VAL_SQ = re.compile(r"'((?:\\'|[^'])*)'")
_ENV_VAL_DQ = re.compile(r'"((?:\\"|[^"])*)"')
_ENV_VAL_UQ = re.compile(r"[^\r\n]*")
_ENV_INLINE_COMMENT = re.compile(r"\s+#.*")
_ENV_EOL = re.compile(rf"{_HWS}*(?:\r\n|\n|\r|$)")
_ENV_REST_OF_LINE = re.compile(r"[^\r\n]*(?:\r|\n|\r\n)?")
_ENV_SQ_ESCAPES = re.compile(r"\\[\\']")
_ENV_DQ_ESCAPES = re.compile(r"\\[\\'\"abfnrtv]")
_ENV_VARIABLE = re.compile(r"\$\{(?P<name>[^\}:]*)(?::-(?P<default>[^\}]*))?\}")


_DOTENV_LOADED_VALUES: dict[str, str] = {}


class _EnvParseError(Exception):
    pass


def _decode_escapes(pattern: re.Pattern[str], value: str) -> str:
    return pattern.sub(
        lambda match: codecs.decode(match.group(0), "unicode-escape"), value
    )


def _parse_env_bindings(text: str) -> list[tuple[str, str | None]]:
    """Port of dotenv.parser.parse_binding/parse_stream (same regexes)."""
    pairs: list[tuple[str, str | None]] = []
    pos = 0
    length = len(text)

    def take(regex: re.Pattern[str]) -> re.Match[str]:
        nonlocal pos
        match = regex.match(text, pos)
        if match is None:
            raise _EnvParseError(regex.pattern)
        pos = match.end()
        return match

    def maybe(regex: re.Pattern[str]) -> None:
        nonlocal pos
        match = regex.match(text, pos)
        if match is not None:
            pos = match.end()

    while pos < length:
        maybe(_ENV_WS_ALL)
        if pos >= length:
            break
        try:
            maybe(_ENV_EXPORT)
            if text.startswith("'", pos):
                key = take(_ENV_KEY_Q).group(1)
            else:
                key = take(_ENV_KEY_UQ).group(1)
            maybe(_ENV_HWS)
            value: str | None = None
            if pos < length and text[pos] == "=":
                take(_ENV_EQ)
                char = text[pos] if pos < length else ""
                if char == "'":
                    value = _decode_escapes(_ENV_SQ_ESCAPES, take(_ENV_VAL_SQ).group(1))
                elif char == '"':
                    value = _decode_escapes(_ENV_DQ_ESCAPES, take(_ENV_VAL_DQ).group(1))
                elif char in ("", "\n", "\r"):
                    value = ""
                else:
                    part = take(_ENV_VAL_UQ).group(0)
                    value = _ENV_INLINE_COMMENT.sub("", part).rstrip()
            take(_ENV_EOL)
        except _EnvParseError:
            maybe(_ENV_REST_OF_LINE)
            continue
        # Bare words without '=' parse to value=None in dotenv; they never
        # mutate os.environ and resolve to "" during interpolation, so they
        # are dropped here.
        if value is not None:
            pairs.append((key, value))
    return pairs


def _load_env_file(path: Path | str) -> None:
    """Apply a .env file to os.environ like dotenv.load_dotenv(path).

    override=False semantics: pre-existing environment variables always win.
    """
    text = Path(path).read_text(encoding="utf-8")
    parsed: dict[str, str] = {}

    def resolve(match: re.Match[str]) -> str:
        # override=False order: earlier file values, then os.environ on top.
        found = lookup.get(match["name"])
        if found is not None:
            return found
        default = match["default"]
        return default if default is not None else ""

    for key, raw in _parse_env_bindings(text):
        lookup: dict[str, str] = dict(parsed)
        lookup.update(os.environ)
        parsed[key] = _ENV_VARIABLE.sub(resolve, raw)
    for key, value in parsed.items():
        if key not in os.environ and value is not None:
            os.environ[key] = value
            _DOTENV_LOADED_VALUES[key] = value


def value_loaded_from_dotenv(key: str) -> bool:
    """Return whether the current value was written by this module's `.env` loader."""
    return key in _DOTENV_LOADED_VALUES and os.environ.get(key) == _DOTENV_LOADED_VALUES[key]


def _find_dotenv(start: Path) -> Path | None:
    """Same discovery as dotenv.find_dotenv(usecwd=False): walk up."""
    for directory in (start, *start.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


_dotenv_path = _find_dotenv(Path(__file__).resolve().parent)
if _dotenv_path is not None:
    _load_env_file(_dotenv_path)

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "botquanganh-host-mcp"
VERSION = "2.0.0"

MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "18427"))
MCP_JSON_RESPONSE = os.getenv("MCP_JSON_RESPONSE", "true").lower() == "true"
MCP_STATELESS_HTTP = os.getenv("MCP_STATELESS_HTTP", "true").lower() == "true"
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
ALLOWED_ORIGINS = tuple(
    x.strip()
    for x in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if x.strip()
)

HOST_WORKSPACE_DIR = Path(os.getenv("HOST_WORKSPACE_DIR", str(Path.home()))).expanduser()
if not HOST_WORKSPACE_DIR.is_absolute():
    HOST_WORKSPACE_DIR = BASE_DIR / HOST_WORKSPACE_DIR
HOST_WORKSPACE_DIR = HOST_WORKSPACE_DIR.resolve()
HOST_RESTRICT_TO_WORKSPACE = (
    os.getenv("HOST_RESTRICT_TO_WORKSPACE", "true").lower() == "true"
)

HOST_DEFAULT_DIR = Path(os.getenv("HOST_DEFAULT_DIR", str(HOST_WORKSPACE_DIR))).expanduser()
if not HOST_DEFAULT_DIR.is_absolute():
    HOST_DEFAULT_DIR = BASE_DIR / HOST_DEFAULT_DIR
HOST_DEFAULT_DIR = HOST_DEFAULT_DIR.resolve()

if HOST_RESTRICT_TO_WORKSPACE:
    try:
        HOST_DEFAULT_DIR.relative_to(HOST_WORKSPACE_DIR)
    except ValueError:
        HOST_DEFAULT_DIR = HOST_WORKSPACE_DIR

# --- Scoped permissions ------------------------------------------------------
# Read and write operations can be scoped independently. Both scopes fall back
# to the resolved HOST_WORKSPACE_DIR so behavior is unchanged until an operator
# sets HOST_READ_SCOPE / HOST_WRITE_SCOPE / HOST_READ_DENY_GLOBS explicitly.
# The *_SET flags record whether the key was actually provided so callers can
# tell an explicit override apart from the fallback value.


def _resolve_config_path(raw: str, fallback: Path) -> Path:
    """Resolve a path-valued setting the way HOST_WORKSPACE_DIR is resolved."""
    candidate = Path(raw if raw else str(fallback)).expanduser()
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


_HOST_READ_SCOPE_RAW = os.getenv("HOST_READ_SCOPE", "").strip()
_HOST_WRITE_SCOPE_RAW = os.getenv("HOST_WRITE_SCOPE", "").strip()
HOST_READ_SCOPE_SET = bool(_HOST_READ_SCOPE_RAW)
HOST_WRITE_SCOPE_SET = bool(_HOST_WRITE_SCOPE_RAW)
HOST_READ_SCOPE = _resolve_config_path(_HOST_READ_SCOPE_RAW, HOST_WORKSPACE_DIR)
HOST_WRITE_SCOPE = _resolve_config_path(_HOST_WRITE_SCOPE_RAW, HOST_WORKSPACE_DIR)
HOST_READ_DENY_GLOBS = [
    item.strip()
    for item in os.getenv("HOST_READ_DENY_GLOBS", "").split(",")
    if item.strip()
]

def _positive_int_env(key: str, default: str) -> int:
    """Read a safety-critical positive integer setting."""
    try:
        parsed = int(os.getenv(key, default) or default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{key} must be a positive integer (>= 1).")
    return parsed


def _non_negative_int_env(key: str, default: str) -> int:
    """Read a non-negative integer setting."""
    try:
        parsed = int(os.getenv(key, default) or default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{key} must be a non-negative integer (>= 0).")
    return parsed


def _finite_non_negative_float_env(key: str, default: str) -> float:
    """Read a finite non-negative float setting.

    Reject NaN and infinity from `.env` values.
    """
    raw = os.getenv(key, default) or default
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a finite number (>= 0).") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{key} must be a finite number (>= 0).")
    if parsed < 0:
        raise ValueError(f"{key} must be a finite number (>= 0).")
    return parsed


WORKSPACE_SEARCH_MAX_WORK_MATCHES = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_WORK_MATCHES", "20000"
)
WORKSPACE_SEARCH_MAX_SCANNED_FILES = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_SCANNED_FILES", "20000"
)
WORKSPACE_SEARCH_MAX_SCANNED_BYTES = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_SCANNED_BYTES", "200000000"
)
WORKSPACE_SEARCH_MAX_CONCURRENT = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_CONCURRENT", "4"
)
WORKSPACE_SEARCH_MAX_PER_CHAT = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_PER_CHAT", "2"
)
WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS = _finite_non_negative_float_env(
    "WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS", "2"
)
WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES = _positive_int_env(
    "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES", "100"
)
WORKSPACE_SEARCH_MAX_RETURNED_MATCHES = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES", "500"
)
WORKSPACE_SEARCH_MAX_LINE_CHARS = _positive_int_env(
    "WORKSPACE_SEARCH_MAX_LINE_CHARS", "8192"
)
MCP_MAX_PAYLOAD_BYTES = _positive_int_env("MCP_MAX_PAYLOAD_BYTES", "512000")
if MCP_MAX_PAYLOAD_BYTES < 1024:
    raise ValueError("MCP_MAX_PAYLOAD_BYTES must be >= 1024.")
MCP_TOOL_RESULT_OVERHEAD_BYTES = _non_negative_int_env(
    "MCP_TOOL_RESULT_OVERHEAD_BYTES", "4096"
)
if MCP_TOOL_RESULT_OVERHEAD_BYTES > MCP_MAX_PAYLOAD_BYTES:
    raise ValueError(
        "MCP_TOOL_RESULT_OVERHEAD_BYTES must be <= MCP_MAX_PAYLOAD_BYTES."
    )
if WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES > WORKSPACE_SEARCH_MAX_RETURNED_MATCHES:
    raise ValueError(
        "WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES must be <= "
        "WORKSPACE_SEARCH_MAX_RETURNED_MATCHES."
    )

HOST_COMMAND_POLICY = os.getenv("HOST_COMMAND_POLICY", "guarded").strip().lower()
if HOST_COMMAND_POLICY not in {"guarded", "allowlist"}:
    raise ValueError("HOST_COMMAND_POLICY must be 'guarded' or 'allowlist'")
HOST_ALLOWED_COMMANDS = [
    item.strip()
    for item in os.getenv("HOST_ALLOWED_COMMANDS", "all").split(",")
    if item.strip()
]
HOST_INHERIT_ENV = os.getenv("HOST_INHERIT_ENV", "true").lower() == "true"
HOST_ENV_ALLOWLIST = [
    item.strip()
    for item in os.getenv("HOST_ENV_ALLOWLIST", "").split(",")
    if item.strip()
]

HOST_KNOWLEDGE_DIR = Path(
    os.getenv("HOST_KNOWLEDGE_DIR", str(BASE_DIR / "knowledge"))
).expanduser()
if not HOST_KNOWLEDGE_DIR.is_absolute():
    HOST_KNOWLEDGE_DIR = BASE_DIR / HOST_KNOWLEDGE_DIR
HOST_KNOWLEDGE_DIR = HOST_KNOWLEDGE_DIR.resolve()
HOST_TOOL_CACHE_SECONDS = max(0, int(os.getenv("HOST_TOOL_CACHE_SECONDS", "300")))

MAX_SINGLE_FILE_BYTES = int(os.getenv("MAX_SINGLE_FILE_BYTES", "3000000"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", "500000"))
MAX_WORKSPACE_EXPLORE_ENTRIES = max(
    1, int(os.getenv("MAX_WORKSPACE_EXPLORE_ENTRIES", "100"))
)
DEFAULT_TIMEOUT_SECONDS = max(0, int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "60")))
MAX_TIMEOUT_SECONDS = max(0, int(os.getenv("MAX_TIMEOUT_SECONDS", "300")))
MAX_CONCURRENT_COMMANDS = max(1, int(os.getenv("MAX_CONCURRENT_COMMANDS", "100")))

COMMAND_QUEUE_TIMEOUT_SECONDS = _finite_non_negative_float_env(
    "COMMAND_QUEUE_TIMEOUT_SECONDS", "2"
)
SEARCH_TEXT_DEADLINE_SECONDS = _finite_non_negative_float_env(
    "SEARCH_TEXT_DEADLINE_SECONDS", "15"
)

LOG_FILE = Path(os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "gateway.log")))
if not LOG_FILE.is_absolute():
    LOG_FILE = BASE_DIR / LOG_FILE
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_MAX_BYTES = max(1024, int(os.getenv("AUDIT_LOG_MAX_BYTES", "10000000")))
AUDIT_LOG_BACKUP_COUNT = max(1, int(os.getenv("AUDIT_LOG_BACKUP_COUNT", "5")))
AUDIT_MAX_FIELD_CHARS = max(256, int(os.getenv("AUDIT_MAX_FIELD_CHARS", "4000")))

# --- Attribution and chat workspaces -----------------------------------------
# These settings are consumed by host attribution, workspace binding, lifecycle
# sweeping, REST activity, and workspace-management CLI paths. Defaults keep
# the opt-in workspace/isolation behavior disabled for existing installations.

ATTRIBUTION_MODE = os.getenv("ATTRIBUTION_MODE", "enforce").strip().lower()
if ATTRIBUTION_MODE not in {"off", "tag", "strict", "enforce"}:
    raise ValueError(
        "ATTRIBUTION_MODE must be one of 'off', 'tag', 'strict', 'enforce'"
    )

HOST_CHAT_WORKSPACES = os.getenv("HOST_CHAT_WORKSPACES", "true").lower() == "true"
HOST_CHAT_ROOT = _resolve_config_path(
    os.getenv("HOST_CHAT_ROOT", "").strip(),
    Path("~/Downloads/bqa-workspaces"),
)
HOST_CHAT_IDLE_ARCHIVE_HOURS = max(
    0, int(os.getenv("HOST_CHAT_IDLE_ARCHIVE_HOURS", "72"))
)
HOST_CHAT_RETENTION_DAYS = max(0, int(os.getenv("HOST_CHAT_RETENTION_DAYS", "30")))
HOST_CHAT_MAX_WORKSPACES = max(1, int(os.getenv("HOST_CHAT_MAX_WORKSPACES", "128")))
HOST_CHAT_QUOTA_MB = max(0, int(os.getenv("HOST_CHAT_QUOTA_MB", "2048")))
HOST_CHAT_ISOLATE = os.getenv("HOST_CHAT_ISOLATE", "false").lower() == "true"
HOST_CHAT_AUTH_MODE = os.getenv("HOST_CHAT_AUTH_MODE", "trust_gateway").strip().lower()
HOST_CHAT_RESUME_HINT_MINUTES = max(
    0, int(os.getenv("HOST_CHAT_RESUME_HINT_MINUTES", "30"))
)
HOST_CHAT_ROOT_MAX_GB = max(0.0, float(os.getenv("HOST_CHAT_ROOT_MAX_GB", "24")))
HOST_CHAT_JOURNAL_MAX_BYTES = max(
    1024, int(os.getenv("HOST_CHAT_JOURNAL_MAX_BYTES", "8388608"))
)
HOST_TRASH_DIR = _resolve_config_path(
    os.getenv("HOST_TRASH_DIR", "").strip(),
    Path("~/Downloads/bqa-trash"),
)

# --- Background Task Management (Super-Tool 'task') ---------------------------
HOST_TASK_MAX_PER_CHAT = max(1, int(os.getenv("HOST_TASK_MAX_PER_CHAT", "3")))
HOST_TASK_MAX_GLOBAL = max(1, int(os.getenv("HOST_TASK_MAX_GLOBAL", "10")))
HOST_TASK_WAIT_BEFORE_ASYNC_MS = max(
    500, int(os.getenv("HOST_TASK_WAIT_BEFORE_ASYNC_MS", "5000"))
)
HOST_TASK_MAX_TAIL_BYTES = max(
    1024, int(os.getenv("HOST_TASK_MAX_TAIL_BYTES", "65536"))
)
HOST_TASK_LOG_MAX_BYTES = max(
    65536, int(os.getenv("HOST_TASK_LOG_MAX_BYTES", "2097152"))
)
HOST_TASK_KILL_GRACE_SECONDS = max(
    1, int(os.getenv("HOST_TASK_KILL_GRACE_SECONDS", "3"))
)
