import time
import socket
import ssl
from typing import Any, Dict, Optional
from app.mcp_server import mcp
from app.security import (
    validate_target_allowlisted,
    block_private_or_local_host,
    resolve_host_to_ips,
    format_error_response
)
from app.logging_audit import log_audit_event


@mcp.tool(
    name="check_target_allowed",
    description="Check if a target host:port is permitted by allowlist and security policy rules before requesting a fallback execution."
)
def check_target_allowed(host: str, port: int) -> Dict[str, Any]:
    """Checks target allowlist status and policy blocks."""
    try:
        # Check target allowlisted
        validate_target_allowlisted(host, port)
        # Check block private/local
        block_private_or_local_host(host, port)
        return {
            "ok": True,
            "allowed": True,
            "policy": "ALLOWED_TCP_TARGETS",
            "message": f"Target '{host}:{port}' is allowed."
        }
    except Exception as e:
        err = format_error_response(e)
        return {
            "ok": False,
            "allowed": False,
            "error": err["error"]
        }


@mcp.tool(
    name="probe_target_from_runner",
    description=(
        "Check TCP connectivity and diagnostic information to a target from your runner machine. "
        "Only valid after experiencing a remote connection failure inside the LLM sandbox. "
        "Requires target to be allowlisted."
    )
)
def probe_target_from_runner(
    target: Dict[str, Any],
    sandbox_failure_reason: str
) -> Dict[str, Any]:
    """Probes connectivity to the remote target host:port and attempts to read a banner and perform network diagnostics."""
    try:
        if not sandbox_failure_reason or not sandbox_failure_reason.strip():
            raise ValueError("sandbox_failure_reason must be provided to probe target.")
            
        host = target.get("host")
        port = target.get("port")
        if not host or port is None:
            raise ValueError("Target host and port must be specified in the target field.")
            
        # Security validations
        validate_target_allowlisted(host, port)
        block_private_or_local_host(host, port)
        
        log_audit_event("PROBE_TARGET_REQUEST", {
            "target": f"{host}:{port}",
            "sandbox_failure_reason": sandbox_failure_reason
        })
        
        start_time = time.time()
        reachable = False
        banner: Optional[str] = None
        
        # DNS diagnostic
        ips = resolve_host_to_ips(host)
        dns_ok = len(ips) > 0
        
        # TCP/TLS diagnostics
        tcp_connected = False
        tcp_duration_ms = 0
        tls_attempted = False
        tls_handshake_ok = False
        
        if dns_ok:
            tcp_start = time.time()
            try:
                # Attempt TCP connection
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5.0)  # 5 seconds connection timeout
                s.connect((host, int(port)))
                tcp_connected = True
                reachable = True
                tcp_duration_ms = int((time.time() - tcp_start) * 1000)
                
                # Trước khi wrap TLS, đọc banner trước nếu không phải 443
                if port != 443:
                    s.settimeout(1.0)
                    try:
                        banner_bytes = s.recv(1024)
                        if banner_bytes:
                            banner = banner_bytes.decode('utf-8', errors='replace')
                    except Exception:
                        pass

                # Attempt TLS Handshake if it's HTTPS (443)
                if port == 443:
                    tls_attempted = True
                    try:
                        context = ssl.create_default_context()
                        with context.wrap_socket(s, server_hostname=host) as ss:
                            tls_handshake_ok = True
                    except Exception:
                        pass
            except Exception as conn_err:
                log_audit_event("PROBE_TARGET_FAILED_CONNECTION", {
                    "target": f"{host}:{port}",
                    "error": str(conn_err)
                })
            finally:
                try:
                    s.close()
                except Exception:
                    pass
                
        duration_ms = int((time.time() - start_time) * 1000)
        
        return {
            "ok": True,
            "reachable": reachable,
            "banner": banner,
            "duration_ms": duration_ms,
            "dns": {
                "resolved": dns_ok,
                "addresses": ips
            },
            "tcp": {
                "connected": tcp_connected,
                "duration_ms": tcp_duration_ms
            },
            "tls": {
                "attempted": tls_attempted,
                "handshake_ok": tls_handshake_ok,
                "server_name": host if tls_attempted else None
            }
        }
        
    except Exception as e:
        log_audit_event("PROBE_ERROR", {"error": str(e)})
        return format_error_response(e)


@mcp.tool(
    name="tcp_connect_ssl",
    description=(
        "Open an SSL/TLS TCP connection to an allowlisted host:port, optionally send lines, and capture the response. "
        "Useful for challenge services that are normally tested with ncat --ssl."
    )
)
def tcp_connect_ssl(
    host: str,
    port: int,
    send_lines: Optional[list[str]] = None,
    server_name: Optional[str] = None,
    recv_bytes: int = 4096,
    timeout_seconds: int = 10,
) -> Dict[str, Any]:
    try:
        validate_target_allowlisted(host, port)
        block_private_or_local_host(host, port)

        if send_lines is None:
            send_lines = []
        recv_bytes = max(1, min(int(recv_bytes), 65536))
        timeout_seconds = max(1, min(int(timeout_seconds), 30))

        context = ssl.create_default_context()
        transcript = []
        peer = {}
        response_bytes = b""

        with socket.create_connection((host, int(port)), timeout=timeout_seconds) as sock:
            with context.wrap_socket(sock, server_hostname=server_name or host) as ssock:
                ssock.settimeout(timeout_seconds)
                cert = ssock.getpeercert()
                peer = {
                    "cipher": ssock.cipher(),
                    "version": ssock.version(),
                    "server_name": server_name or host,
                    "peer_subject": cert.get("subject", []),
                }
                for line in send_lines:
                    payload = line if line.endswith("\n") else line + "\n"
                    ssock.sendall(payload.encode("utf-8"))
                    transcript.append({"direction": "send", "data": payload})
                try:
                    response_bytes = ssock.recv(recv_bytes)
                except socket.timeout:
                    response_bytes = b""

        response_text = response_bytes.decode("utf-8", errors="replace")
        if response_text:
            transcript.append({"direction": "recv", "data": response_text})

        log_audit_event("TCP_CONNECT_SSL", {
            "target": f"{host}:{port}",
            "send_lines": len(send_lines),
            "received_bytes": len(response_bytes),
        })
        return {
            "ok": True,
            "target": f"{host}:{port}",
            "peer": peer,
            "response": response_text,
            "received_bytes": len(response_bytes),
            "transcript": transcript,
        }
    except Exception as e:
        log_audit_event("TCP_CONNECT_SSL_FAIL", {"target": f"{host}:{port}", "error": str(e)})
        return format_error_response(e)
