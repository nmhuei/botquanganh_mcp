import time
import socket
from typing import Any, Dict, Optional
from app.mcp_server import mcp
from app.security import validate_target_allowlisted, block_private_or_local_host
from app.logging_audit import log_audit_event

@mcp.tool(
    name="probe_target_from_runner",
    description=(
        "Check TCP connectivity to a target from your runner machine. "
        "Only valid after experiencing a remote connection failure inside the LLM sandbox. "
        "Requires target to be allowlisted."
    )
)
def probe_target_from_runner(
    target: Dict[str, Any],
    sandbox_failure_reason: str
) -> Dict[str, Any]:
    """Probes connectivity to the remote target host:port and attempts to read a banner."""
    try:
        # 1. Input validation
        if not sandbox_failure_reason or not sandbox_failure_reason.strip():

            raise ValueError("sandbox_failure_reason must be provided to probe target.")
            
        host = target.get("host")
        port = target.get("port")
        if not host or port is None:
            raise ValueError("Target host and port must be specified in the target field.")
            
        # 3. Security validations
        validate_target_allowlisted(host, port)
        block_private_or_local_host(host, port)
        
        log_audit_event("PROBE_TARGET_REQUEST", {
            "target": f"{host}:{port}",
            "sandbox_failure_reason": sandbox_failure_reason
        })
        
        start_time = time.time()
        reachable = False
        banner: Optional[str] = None
        
        try:
            # 4. Attempt TCP connection
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)  # 5 seconds connection timeout
            s.connect((host, int(port)))
            reachable = True
            
            # Attempt to read a banner with a 1-second timeout
            s.settimeout(1.0)
            try:
                banner_bytes = s.recv(1024)
                if banner_bytes:
                    banner = banner_bytes.decode('utf-8', errors='replace')
            except socket.timeout:
                pass  # No banner returned in 1s is normal for some services
            except Exception:
                pass
            finally:
                s.close()
        except Exception as conn_err:
            log_audit_event("PROBE_TARGET_FAILED_CONNECTION", {
                "target": f"{host}:{port}",
                "error": str(conn_err)
            })
            
        duration_ms = int((time.time() - start_time) * 1000)
        
        return {
            "ok": True,
            "reachable": reachable,
            "banner": banner,
            "duration_ms": duration_ms
        }
        
    except Exception as e:
        log_audit_event("PROBE_ERROR", {"error": str(e)})
        raise e
