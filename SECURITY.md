# Security Policy

This document outlines the security architecture, threat model, and mitigation strategies implemented in the Fallback Runner MCP server.

---

## 1. Threat Model & Mitigations

### Threat: Arbitrary Remote Code Execution (RCE) on the Host Machine
- **Risk**: An LLM agent or attacker sending a malicious solver payload could attempt to execute commands directly on the host operating system, leading to host compromise.
- **Mitigation**:
  - **Docker Isolation**: The solver script runs inside a container with resources restricted (`--memory 512m`, `--cpus 1`, `--pids-limit 128`).
  - **Privilege Dropping**: Containers run under a non-root runner user (`runner` uid 1000) and drop all Linux capabilities (`--cap-drop ALL`).
  - **No Host Shell**: Command execution uses `subprocess.run(shell=False)` with a strict schema constraint, meaning the entrypoint can only be invoked through `python3 solve.py` or `sage solve.py` with validated individual arguments.

### Threat: Malicious Outbound Requests (SSRF / Network Scanning)
- **Risk**: A solver script could attempt to scan the local home network, access cloud metadata services (e.g., `169.254.169.254`), or connect to arbitrary ports on loopback.
- **Mitigation**:
  - **Private IP Rejection**: Rejects any target hosts that resolve to private, loopback, or link-local IP addresses (e.g. RFC 1918, RFC 4193).
  - **Target Allowlisting**: Rejects execution unless the `host:port` is explicitly listed in `ALLOWED_TCP_TARGETS`.
  - **Dynamic Egress Firewall**: When `ENABLE_EGRESS_FIREWALL=true`, the server dynamically inserts iptables rules on the host to drop all outbound packets from the container's IP address *except* TCP traffic destined to the resolved target IP and port.

### Threat: File System Escape & Write Attacks
- **Risk**: A solver payload containing path traversal strings (e.g. `../../etc/passwd` or `~/.ssh/id_rsa`) could overwrite or read sensitive system files on the host machine.
- **Mitigation**:
  - **Path Traversal Blocking**: Absolute paths and paths containing parent directory segments (`..`) are strictly blocked.
  - **Isolated Volume Mounting**: Only the dedicated run input folder (`logs/runs/<run_id>/input`) is mounted to the container's `/work` directory. No root directories or user home folders are ever mounted.
  - **Size Limits**: Total payload size is limited to `MAX_CODE_BYTES` (5MB default) to prevent disk space exhaustion.

### Threat: Credential Leaking in Logs
- **Risk**: Solver scripts or request headers might print out session tokens, passwords, cookies, or private SSH keys. If written directly to logs, these could be exposed.
- **Mitigation**:
  - **Recursive Log Redaction**: The audit logging system recursively parses log payloads and replaces values associated with common credential keywords (e.g., `token`, `password`, `cookie`, `secret`, `private_key`) with `[REDACTED]`.
  - **Key Block Redaction**: Text structures that look like private key blocks or SSH keys are automatically replaced with `[REDACTED KEY MATERIAL]`.

---

## 2. Hardening for Production Use

If you plan to deploy this server permanently (e.g., on a public VPS):

1. **Do not use the static token**. Instead, configure OAuth authentication to control which clients can access your connector.
2. **Reverse Proxying**: Always wrap the SSE endpoint behind Caddy, Nginx, or Cloudflare Tunnel to enforce HTTPS.
3. **Turn on the Egress Firewall**: Set `ENABLE_EGRESS_FIREWALL=true` in `.env` to prevent containers from connecting to other servers on the internet.
4. **Regular Cleanups**: Ensure the `scripts/cleanup_runs.sh` script runs as a daily cron job to delete old execution directories.
