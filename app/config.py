import codecs
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
VERSION = "1.0.0"

MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "18427"))
MCP_JSON_RESPONSE = os.getenv("MCP_JSON_RESPONSE", "true").lower() == "true"
MCP_STATELESS_HTTP = os.getenv("MCP_STATELESS_HTTP", "true").lower() == "true"
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

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
MAX_TIMEOUT_SECONDS = int(os.getenv("MAX_TIMEOUT_SECONDS", "60"))
MAX_CONCURRENT_COMMANDS = max(1, int(os.getenv("MAX_CONCURRENT_COMMANDS", "100")))
COMMAND_QUEUE_TIMEOUT_SECONDS = max(
    0.0, float(os.getenv("COMMAND_QUEUE_TIMEOUT_SECONDS", "2"))
)

LOG_FILE = Path(os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "gateway.log")))
if not LOG_FILE.is_absolute():
    LOG_FILE = BASE_DIR / LOG_FILE
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_MAX_BYTES = max(1024, int(os.getenv("AUDIT_LOG_MAX_BYTES", "10000000")))
AUDIT_LOG_BACKUP_COUNT = max(1, int(os.getenv("AUDIT_LOG_BACKUP_COUNT", "5")))
AUDIT_MAX_FIELD_CHARS = max(256, int(os.getenv("AUDIT_MAX_FIELD_CHARS", "4000")))
