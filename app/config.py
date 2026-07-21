import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "botquanganh-host-mcp"
VERSION = "1.0.0"

MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_JSON_RESPONSE = os.getenv("MCP_JSON_RESPONSE", "true").lower() == "true"
MCP_STATELESS_HTTP = os.getenv("MCP_STATELESS_HTTP", "true").lower() == "true"
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

HOST_WORKSPACE_DIR = Path(os.getenv("HOST_WORKSPACE_DIR", str(Path.home()))).expanduser()
if not HOST_WORKSPACE_DIR.is_absolute():
    HOST_WORKSPACE_DIR = BASE_DIR / HOST_WORKSPACE_DIR
HOST_WORKSPACE_DIR = HOST_WORKSPACE_DIR.resolve()
HOST_RESTRICT_TO_WORKSPACE = (
    os.getenv("HOST_RESTRICT_TO_WORKSPACE", "true").lower() == "true"
)

HOST_COMMAND_POLICY = os.getenv("HOST_COMMAND_POLICY", "guarded").strip().lower()
if HOST_COMMAND_POLICY not in {"guarded", "allowlist"}:
    raise ValueError("HOST_COMMAND_POLICY must be 'guarded' or 'allowlist'")
HOST_ALLOWED_COMMANDS = [
    item.strip()
    for item in os.getenv("HOST_ALLOWED_COMMANDS", "").split(",")
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
MAX_CONCURRENT_COMMANDS = max(1, int(os.getenv("MAX_CONCURRENT_COMMANDS", "4")))
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

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "200"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_CLIENTS = max(1, int(os.getenv("RATE_LIMIT_MAX_CLIENTS", "10000")))
