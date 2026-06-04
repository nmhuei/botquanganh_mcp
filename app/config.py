import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root path (where app/ is located)
BASE_DIR = Path(__file__).resolve().parent.parent

# MCP binding settings
MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

# Gateway authentication token (optional)
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")

# Allowed TCP Targets
ALLOWED_TCP_TARGETS = [t.strip() for t in os.getenv("ALLOWED_TCP_TARGETS", "").split(",") if t.strip()]

# Directories
RUNS_DIR = Path(os.getenv("RUNS_DIR", "./logs/runs"))
if not RUNS_DIR.is_absolute():
    RUNS_DIR = BASE_DIR / RUNS_DIR
RUNS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = Path(os.getenv("LOG_FILE", "./logs/gateway.log"))
if not LOG_FILE.is_absolute():
    LOG_FILE = BASE_DIR / LOG_FILE
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Limit policies
MAX_CODE_BYTES = int(os.getenv("MAX_CODE_BYTES", "5000000"))
MAX_SINGLE_FILE_BYTES = int(os.getenv("MAX_SINGLE_FILE_BYTES", "3000000"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", "500000"))
MAX_TIMEOUT_SECONDS = int(os.getenv("MAX_TIMEOUT_SECONDS", "60"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "30"))
MAX_ARGS = int(os.getenv("MAX_ARGS", "16"))
MAX_ARG_LENGTH = int(os.getenv("MAX_ARG_LENGTH", "200"))

# Security flags
REQUIRE_SANDBOX_FAILURE_REASON = os.getenv("REQUIRE_SANDBOX_FAILURE_REASON", "true").lower() == "true"
REQUIRE_LOCAL_VALIDATION = os.getenv("REQUIRE_LOCAL_VALIDATION", "true").lower() == "true"
BLOCK_PRIVATE_IPS = os.getenv("BLOCK_PRIVATE_IPS", "true").lower() == "true"
ENABLE_EGRESS_FIREWALL = os.getenv("ENABLE_EGRESS_FIREWALL", "false").lower() == "true"
DELETE_RUN_FILES_AFTER_DAYS = int(os.getenv("DELETE_RUN_FILES_AFTER_DAYS", "7"))

# Docker parameters
RUNNER_IMAGE_PYTHON = os.getenv("RUNNER_IMAGE_PYTHON", "ctf-python-runner:latest")
RUNNER_IMAGE_PWN = os.getenv("RUNNER_IMAGE_PWN", "ctf-pwn-runner:latest")
RUNNER_IMAGE_SAGE = os.getenv("RUNNER_IMAGE_SAGE", "ctf-sage-runner:latest")

DOCKER_MEMORY = os.getenv("DOCKER_MEMORY", "512m")
DOCKER_CPUS = os.getenv("DOCKER_CPUS", "1")
DOCKER_PIDS_LIMIT = int(os.getenv("DOCKER_PIDS_LIMIT", "128"))
DOCKER_USER = os.getenv("DOCKER_USER", "1000:1000")
