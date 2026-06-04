from datetime import datetime
from app.mcp_server import mcp
from app.config import (
    RUNNER_IMAGE_PYTHON,
    RUNNER_IMAGE_PWN,
    RUNNER_IMAGE_SAGE,
    MAX_TIMEOUT_SECONDS,
    MAX_CODE_BYTES,
    MAX_SINGLE_FILE_BYTES,
    MAX_ARGS,
    MAX_ARG_LENGTH,
)
from app.logging_audit import log_audit_event
from app.security import format_error_response


@mcp.tool(name="health_check", description="Verify the MCP server is reachable and running correctly.")
def health_check() -> dict:
    """Verifies connection health and configured runner capabilities."""
    try:
        log_audit_event("HEALTH_CHECK_PASS", {})
        return {
            "ok": True,
            "service": "fallback-runner-mcp",
            "version": "0.2.0",
            "server_time": datetime.utcnow().isoformat() + "Z",
            "runner_images": [RUNNER_IMAGE_PYTHON, RUNNER_IMAGE_PWN, RUNNER_IMAGE_SAGE]
        }
    except Exception as e:
        log_audit_event("HEALTH_CHECK_FAIL", {"tool": "health_check", "error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="get_capabilities",
    description="Retrieve runner constraints, limits, accepted encodings, and feature support matrices."
)
def get_capabilities() -> dict:
    """Returns capabilities and restrictions of the fallback runner server."""
    try:
        log_audit_event("GET_CAPABILITIES", {})
        return {
            "ok": True,
            "service": "fallback-runner-mcp",
            "version": "0.2.0",
            "limits": {
                "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
                "max_total_file_bytes": MAX_CODE_BYTES,
                "max_single_file_bytes": MAX_SINGLE_FILE_BYTES,
                "max_args": MAX_ARGS,
                "max_arg_length": MAX_ARG_LENGTH,
                "accepted_file_encodings": ["text", "base64"]
            },
            "supported_languages": ["python", "pwn", "sage"],
            "features": {
                "validate_only": True,
                "rerun": True,
                "interactive_runs": False,
                "artifact_upload": True,
                "stdout_tail": True,
                "stderr_tail": True
            },
            "network_policy": {
                "allowlist_required": True
            }
        }
    except Exception as e:
        log_audit_event("GET_CAPABILITIES_FAIL", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="get_runner_environments",
    description="Retrieve details about pre-installed programming environments, CTF libraries (Crypto, SageMath, Z3, Pwntools, CloakBrowser), and their usage details."
)
def get_runner_environments() -> dict:
    """Returns a structured dictionary listing the available programming environments,
    pre-installed packages, and importing/execution guides for fallback runs.
    """
    try:
        log_audit_event("GET_RUNNER_ENVIRONMENTS", {})
        return {
            "ok": True,
            "supported_languages": ["python", "pwn", "sage"],
            "environments": {
                "python": {
                    "base_image": RUNNER_IMAGE_PYTHON,
                    "description": "Python 3.12-slim environment for general CTF tasks, web automation/exploitation, and scripting.",
                    "pre_installed_packages": {
                        "pwntools": "CTF/exploit development framework (import pwn)",
                        "pycryptodome": "Cryptography toolkit (import Crypto)",
                        "z3-solver": "SMT solver (import z3)",
                        "libnum": "Number theory utilities (import libnum)",
                        "sympy": "Symbolic mathematics (import sympy)",
                        "gmpy2": "Multiprecision arithmetic (import gmpy2)",
                        "requests": "HTTP requests client (import requests)",
                        "playwright": "Browser automation (import playwright)",
                        "cloakbrowser": "Anti-bot detection Chromium browser client (import cloakbrowser)",
                        "tqdm": "Progress bar utility (import tqdm)",
                        "pyasn1": "ASN.1 parsing library (import pyasn1)",
                        "pyasn1-modules": "ASN.1 modules (import pyasn1_modules)"
                    },
                    "special_notes": [
                        "When using Playwright or CloakBrowser, you MUST launch the browser with the '--no-sandbox' flag because the container runs in root-equivalent/restricted namespaces. Example: cloakbrowser.launch(headless=True, args=['--no-sandbox'])"
                    ]
                },
                "pwn": {
                    "base_image": RUNNER_IMAGE_PWN,
                    "description": "Identical Python 3.12-slim environment equipped with pwntools, z3, pycryptodome, and binary analysis utilities like patchelf, file, gdb, socat, netcat.",
                    "pre_installed_packages": {
                        "pwntools": "CTF/exploit development framework (import pwn)",
                        "pycryptodome": "Cryptography toolkit (import Crypto)",
                        "z3-solver": "SMT solver (import z3)",
                        "libnum": "Number theory utilities (import libnum)",
                        "sympy": "Symbolic mathematics (import sympy)",
                        "gmpy2": "Multiprecision arithmetic (import gmpy2)",
                        "requests": "HTTP requests client (import requests)",
                        "playwright": "Browser automation (import playwright)",
                        "cloakbrowser": "Anti-bot detection Chromium browser client (import cloakbrowser)",
                        "tqdm": "Progress bar utility (import tqdm)",
                        "pyasn1": "ASN.1 parsing library (import pyasn1)",
                        "pyasn1-modules": "ASN.1 modules (import pyasn1_modules)"
                    },
                    "special_notes": [
                        "Equipped with system binaries: netcat-openbsd, socat, file, binutils, patchelf, gdb, git, curl.",
                        "When using Playwright or CloakBrowser, pass args=['--no-sandbox'] to launch() or equivalent functions."
                    ]
                },
                "sage": {
                    "base_image": RUNNER_IMAGE_SAGE,
                    "description": "SageMath environment for cryptanalysis, mathematics, and advanced algebra.",
                    "pre_installed_packages": {
                        "sagemath": "Native SageMath environment (active automatically, run with entrypoint extension .sage or script logic)",
                        "pycryptodome": "Cryptography toolkit (import Crypto)",
                        "z3-solver": "SMT solver (import z3)",
                        "libnum": "Number theory utilities (import libnum)",
                        "sympy": "Symbolic mathematics (import sympy)",
                        "gmpy2": "Multiprecision arithmetic (import gmpy2)",
                        "tqdm": "Progress bar utility (import tqdm)",
                        "pyasn1": "ASN.1 parsing library (import pyasn1)",
                        "pyasn1-modules": "ASN.1 modules (import pyasn1_modules)"
                    },
                    "special_notes": [
                        "Runs directly inside the SageMath python environment.",
                        "Import packages (e.g. z3, Crypto) from within your Sage script normally."
                    ]
                }
            }
        }
    except Exception as e:
        log_audit_event("GET_RUNNER_ENV_FAIL", {"error": str(e)})
        return format_error_response(e)
