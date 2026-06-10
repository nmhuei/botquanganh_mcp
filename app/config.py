import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root path (where app/ is located)
BASE_DIR = Path(__file__).resolve().parent.parent
HOME_WORKSPACE_DIR = Path.home() / "Workspace"

# MCP binding settings
MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

# Gateway authentication token (optional)
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() == "true"

# Allowed TCP Targets
ALLOWED_TCP_TARGETS = [t.strip() for t in os.getenv("ALLOWED_TCP_TARGETS", "").split(",") if t.strip()]
if os.getenv("DISABLE_SECURITY_POLICIES", "false").lower() == "true":
    ALLOWED_TCP_TARGETS = ["*"]

# Directories
RUNS_DIR = Path(os.getenv("RUNS_DIR", "./logs/runs"))
if not RUNS_DIR.is_absolute():
    RUNS_DIR = BASE_DIR / RUNS_DIR
RUNS_DIR.mkdir(parents=True, exist_ok=True)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "./logs/artifacts"))
if not ARTIFACTS_DIR.is_absolute():
    ARTIFACTS_DIR = BASE_DIR / ARTIFACTS_DIR
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

WORKSPACES_DIR = Path(os.getenv("WORKSPACES_DIR", "./logs/workspaces"))
if not WORKSPACES_DIR.is_absolute():
    WORKSPACES_DIR = BASE_DIR / WORKSPACES_DIR
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

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
DISABLE_SECURITY_POLICIES = os.getenv("DISABLE_SECURITY_POLICIES", "false").lower() == "true"
ENABLE_ADVANCED_TOOLS = os.getenv("ENABLE_ADVANCED_TOOLS", "false").lower() == "true"
ENABLE_WORKSPACE_TOOLS = os.getenv("ENABLE_WORKSPACE_TOOLS", "false").lower() == "true"
REQUIRE_SANDBOX_FAILURE_REASON = os.getenv("REQUIRE_SANDBOX_FAILURE_REASON", "true").lower() == "true"
REQUIRE_LOCAL_VALIDATION = os.getenv("REQUIRE_LOCAL_VALIDATION", "true").lower() == "true"
BLOCK_PRIVATE_IPS = os.getenv("BLOCK_PRIVATE_IPS", "true").lower() == "true"
if DISABLE_SECURITY_POLICIES:
    BLOCK_PRIVATE_IPS = False
ENABLE_EGRESS_FIREWALL = os.getenv("ENABLE_EGRESS_FIREWALL", "false").lower() == "true"
DELETE_RUN_FILES_AFTER_DAYS = int(os.getenv("DELETE_RUN_FILES_AFTER_DAYS", "7"))
USE_DOCKER = os.getenv("USE_DOCKER", "true").lower() == "true"


# Agent mode configuration
ENABLE_AGENT_TOOLS = os.getenv("ENABLE_AGENT_TOOLS", "true").lower() == "true"
AGENT_WORKSPACE_DIR_ENV = os.getenv("AGENT_WORKSPACE_DIR", "")
if AGENT_WORKSPACE_DIR_ENV:
    AGENT_WORKSPACE_DIR = Path(AGENT_WORKSPACE_DIR_ENV).expanduser()
    if not AGENT_WORKSPACE_DIR.is_absolute():
        AGENT_WORKSPACE_DIR = BASE_DIR / AGENT_WORKSPACE_DIR
else:
    AGENT_WORKSPACE_DIR = HOME_WORKSPACE_DIR if HOME_WORKSPACE_DIR.exists() else BASE_DIR
AGENT_WORKSPACE_DIR = AGENT_WORKSPACE_DIR.resolve()
AGENT_RESTRICT_TO_WORKSPACE = os.getenv("AGENT_RESTRICT_TO_WORKSPACE", "true").lower() == "true"
if DISABLE_SECURITY_POLICIES:
    AGENT_RESTRICT_TO_WORKSPACE = False

# Enforce RUNS_DIR separation from AGENT_WORKSPACE_DIR
def _is_subdir(path1: Path, path2: Path) -> bool:
    try:
        path1.relative_to(path2)
        return True
    except ValueError:
        return False

runs_dir_resolved = RUNS_DIR.resolve()
if _is_subdir(runs_dir_resolved, AGENT_WORKSPACE_DIR) or _is_subdir(AGENT_WORKSPACE_DIR, runs_dir_resolved):
    # Overriding setting was invalid, fallback to the safe default logs/runs
    default_runs_dir = (BASE_DIR / "logs" / "runs").resolve()
    if _is_subdir(default_runs_dir, AGENT_WORKSPACE_DIR) or _is_subdir(AGENT_WORKSPACE_DIR, default_runs_dir):
        if not DISABLE_SECURITY_POLICIES:
            raise ValueError(
                f"Insecure directory overlap: AGENT_WORKSPACE_DIR ({AGENT_WORKSPACE_DIR}) and RUNS_DIR ({default_runs_dir}) "
                f"must not overlap or be subdirectories of each other."
            )
    RUNS_DIR = default_runs_dir
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
else:
    RUNS_DIR = runs_dir_resolved

# Docker parameters
RUNNER_IMAGE_PYTHON = os.getenv("RUNNER_IMAGE_PYTHON", "ctf-python-runner:latest")
RUNNER_IMAGE_PWN = os.getenv("RUNNER_IMAGE_PWN", "ctf-pwn-runner:latest")
RUNNER_IMAGE_SAGE = os.getenv("RUNNER_IMAGE_SAGE", "ctf-sage-runner:latest")
RUNNER_IMAGE_FORENSICS = os.getenv("RUNNER_IMAGE_FORENSICS", "ctf-forensics-runner:latest")

DOCKER_MEMORY = os.getenv("DOCKER_MEMORY", "512m")
DOCKER_CPUS = os.getenv("DOCKER_CPUS", "1")
DOCKER_PIDS_LIMIT = int(os.getenv("DOCKER_PIDS_LIMIT", "128"))
DOCKER_USER = os.getenv("DOCKER_USER", "1000:1000")
MINIFORGE_PATH = os.getenv("MINIFORGE_PATH", "")
VERSION = "0.3.0"
