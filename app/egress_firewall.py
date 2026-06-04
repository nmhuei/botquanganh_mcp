import socket
import subprocess
from app.config import ENABLE_EGRESS_FIREWALL
from app.logging_audit import log_audit_event

def resolve_target_ip(host: str) -> str:
    """Resolves target host to a single IP address."""
    try:
        addr_info = socket.getaddrinfo(host, None)
        if not addr_info:
            raise ValueError(f"No IP addresses resolved for host '{host}'")
        return addr_info[0][4][0]
    except Exception as e:
        raise ValueError(f"Failed to resolve target host '{host}' for firewall rules: {e}")

def apply_egress_rules(container_ip: str, target_host: str, target_port: int) -> None:
    """Applies iptables rules to permit outbound traffic from container_ip only to target_host:target_port."""
    if not ENABLE_EGRESS_FIREWALL:
        return
        
    if not container_ip:
        raise ValueError("Cannot apply firewall rules: empty container IP address.")
        
    try:
        target_ip = resolve_target_ip(target_host)
        
        # Note: We insert DOCKER-USER rules at position 1. 
        # By inserting the DROP rule at 1, and then inserting the ACCEPT rule at 1,
        # the ACCEPT rule becomes index 1 and the DROP rule becomes index 2.
        # This guarantees that the allow rule takes precedence over the drop rule.
        
        cmd_drop = [
            "sudo", "iptables", "-I", "DOCKER-USER", "1", 
            "-s", container_ip, 
            "-j", "DROP"
        ]
        cmd_allow = [
            "sudo", "iptables", "-I", "DOCKER-USER", "1", 
            "-s", container_ip, 
            "-p", "tcp", "-d", target_ip, "--dport", str(target_port), 
            "-j", "ACCEPT"
        ]
        
        # Execute DROP rule
        res_drop = subprocess.run(cmd_drop, capture_output=True, text=True)
        if res_drop.returncode != 0:
            raise RuntimeError(f"iptables DROP rule error: {res_drop.stderr}")
            
        # Execute ALLOW rule
        res_allow = subprocess.run(cmd_allow, capture_output=True, text=True)
        if res_allow.returncode != 0:
            # Cleanup drop rule if allow rule fails to avoid permanently blocking container
            subprocess.run(["sudo", "iptables", "-D", "DOCKER-USER", "-s", container_ip, "-j", "DROP"])
            raise RuntimeError(f"iptables ALLOW rule error: {res_allow.stderr}")
            
        log_audit_event("FIREWALL_RULES_APPLIED", {
            "container_ip": container_ip,
            "target_ip": target_ip,
            "target_port": target_port
        })
        
    except Exception as e:
        log_audit_event("FIREWALL_ERROR", {"error": str(e)})
        # Fail-closed: raise the error so execution is aborted rather than running unfirewalled
        raise RuntimeError(f"Security error: Egress firewall setup failed. Reason: {e}")

def remove_egress_rules(container_ip: str, target_host: str, target_port: int) -> None:
    """Removes the iptables rules for container_ip."""
    if not ENABLE_EGRESS_FIREWALL:
        return
        
    if not container_ip:
        return
        
    try:
        target_ip = resolve_target_ip(target_host)
        
        cmd_allow = [
            "sudo", "iptables", "-D", "DOCKER-USER", 
            "-s", container_ip, 
            "-p", "tcp", "-d", target_ip, "--dport", str(target_port), 
            "-j", "ACCEPT"
        ]
        cmd_drop = [
            "sudo", "iptables", "-D", "DOCKER-USER", 
            "-s", container_ip, 
            "-j", "DROP"
        ]
        
        # Try to delete both rules. We do not want to raise on errors here to ensure we try deleting both rules.
        subprocess.run(cmd_allow, capture_output=True)
        subprocess.run(cmd_drop, capture_output=True)
        
        log_audit_event("FIREWALL_RULES_REMOVED", {
            "container_ip": container_ip,
            "target_ip": target_ip,
            "target_port": target_port
        })
    except Exception as e:
        log_audit_event("FIREWALL_CLEANUP_ERROR", {"error": str(e)})
