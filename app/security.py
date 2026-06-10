import socket
import ipaddress
from typing import List
from pathlib import PurePosixPath
from app.config import (
    ALLOWED_TCP_TARGETS,
    BLOCK_PRIVATE_IPS,
    MAX_TIMEOUT_SECONDS,
    MAX_ARGS,
    MAX_ARG_LENGTH,
    DISABLE_SECURITY_POLICIES,
)

def is_ip_private(ip_str: str) -> bool:
    """Checks if an IP address string belongs to a private or loopback range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False

def resolve_host_to_ips(host: str) -> List[str]:
    """Resolves a hostname to a list of its IP addresses."""
    try:
        addr_info = socket.getaddrinfo(host, None)
        return list(set(info[4][0] for info in addr_info))
    except socket.gaierror:
        return []

def validate_target_allowlisted(host: str, port: int) -> None:
    """Enforces that the host and port are explicitly allowlisted."""
    if DISABLE_SECURITY_POLICIES:
        return
    if "*" in ALLOWED_TCP_TARGETS:
        return
    target_key = f"{host}:{port}"
    if target_key not in ALLOWED_TCP_TARGETS:
        raise PermissionError(f"Target '{target_key}' is not in the ALLOWED_TCP_TARGETS allowlist.")

def block_private_or_local_host(host: str, port: int) -> None:
    """Blocks requests targeting private IPs or local network endpoints unless explicitly allowlisted."""
    if DISABLE_SECURITY_POLICIES:
        return
    if not BLOCK_PRIVATE_IPS:
        return

    target_key = f"{host}:{port}"
    if target_key in ALLOWED_TCP_TARGETS:
        # Bypassed if administrator explicitly allowlisted this local target for testing
        return

    host_lower = host.lower()
    private_names = {"localhost", "metadata.google.internal", "127.0.0.1", "::1"}
    if host_lower in private_names or host_lower.endswith(".local"):
        raise PermissionError(f"Local or private target hostname '{host}' is blocked.")

    ips = resolve_host_to_ips(host)
    for ip in ips:
        if is_ip_private(ip):
            raise PermissionError(f"Local or private target IP '{ip}' (resolved from '{host}') is blocked.")

def validate_timeout(timeout_seconds: int) -> None:
    """Ensures timeout is within allowed bounds."""
    if DISABLE_SECURITY_POLICIES:
        return
    if timeout_seconds <= 0:
        raise ValueError("Timeout must be greater than 0.")
    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"Requested timeout {timeout_seconds}s exceeds MAX_TIMEOUT_SECONDS ({MAX_TIMEOUT_SECONDS}s).")

def validate_language(language: str) -> None:
    """Ensures the language/runner profile is supported."""
    if DISABLE_SECURITY_POLICIES:
        return
    supported = ["python", "pwn", "sage", "forensics"]
    if language.lower() not in supported:
        raise ValueError(f"Language '{language}' is not supported. Supported: {supported}")

def validate_args(args: List[str]) -> None:
    """Ensures number of arguments and argument lengths are within limits."""
    if DISABLE_SECURITY_POLICIES:
        return
    if len(args) > MAX_ARGS:
        raise ValueError(f"Number of arguments {len(args)} exceeds MAX_ARGS ({MAX_ARGS}).")
    for idx, arg in enumerate(args):
        if len(arg) > MAX_ARG_LENGTH:
            raise ValueError(f"Argument at index {idx} exceeds MAX_ARG_LENGTH ({MAX_ARG_LENGTH} chars).")

def validate_relative_path(path: str) -> None:
    """Prevents absolute path or path traversal attacks."""
    if DISABLE_SECURITY_POLICIES:
        return
    p = PurePosixPath(path)
    if p.is_absolute():
        raise ValueError(f"Absolute path '{path}' is not allowed.")
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: '{path}'")
    if not str(p) or str(p) == ".":
        raise ValueError(f"Invalid empty/dot path: '{path}'")

def format_error_response(e: Exception) -> dict:
    """Standardizes error response formatting according to the proposal's enum and details."""
    code = "INTERNAL_RUNNER_ERROR"
    message = str(e)
    details = {}
    suggestion = "Check system logs or contact server administrator."

    msg = str(e).lower()
    
    # Map Pydantic validation errors
    if "validation error" in msg:
        code = "SCHEMA_INVALID"
        suggestion = "Check the input parameters and format against the tool schema."
        # Attempt to parse field errors if possible
        details["validation_message"] = str(e)
    elif isinstance(e, PermissionError):
        if "not in the allowed_tcp_targets" in msg:
            code = "TARGET_NOT_ALLOWLISTED"
            suggestion = "Check if the remote target hostname and port are allowlisted, or request the administrator to add them to ALLOWED_TCP_TARGETS."
        else:
            code = "POLICY_BLOCKED"
            suggestion = "Verify that the target endpoint is not a private, local, or blocked IP/host address."
            if "blocked_command_rule=" in message:
                for part in message.split(";"):
                    if "=" not in part:
                        continue
                    key, value = part.split("=", 1)
                    details[key.strip()] = value.strip()
                if "suggested_alternative" in details:
                    suggestion = details["suggested_alternative"]
            elif "outside the agent workspace directory" in message:
                details["blocked_reason"] = "cwd_outside_workspace"
            elif "workspace tools are disabled" in msg:
                details["blocked_reason"] = "workspace_mode_disabled"
    elif isinstance(e, ValueError):
        if "timeout" in msg:
            code = "TIMEOUT_INVALID"
            suggestion = "Ensure timeout_seconds is a positive integer below the configured MAX_TIMEOUT_SECONDS."
        elif "language" in msg:
            code = "UNSUPPORTED_LANGUAGE"
            suggestion = "Ensure language is one of: 'python', 'pwn', 'sage'."
        elif "path traversal" in msg or "absolute path" in msg or "invalid empty/dot path" in msg:
            code = "SCHEMA_INVALID"
            suggestion = "Correct your file path parameters to be strictly relative and avoid path traversal."
        elif "encoding must be" in msg:
            code = "UNSUPPORTED_ENCODING"
            suggestion = "Specify file encoding as either 'text' or 'base64'."
        elif "entrypoint" in msg:
            code = "SCHEMA_INVALID"
            suggestion = "Ensure the specified entrypoint is included in the files list."
        else:
            code = "SCHEMA_INVALID"
            suggestion = "Please check your payload formatting and schemas."
    elif isinstance(e, FileNotFoundError):
        code = "RUN_NOT_FOUND"
        suggestion = "The specified run_id was not found. Use list_recent_runs to find correct run_ids."

    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "suggestion": suggestion
        }
    }
