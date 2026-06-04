# Fallback Runner MCP

Fallback Runner MCP is a specialized, secure Model Context Protocol (MCP) server designed to run CTF/lab solvers in isolated Docker containers on your local host **only when the LLM agent's sandbox fails to connect to the remote target**.

It acts as a secure, restricted **Fallback Runner** rather than a general-purpose internet proxy or arbitrary command executor.

---

## 1. How It Works (Standard Workflow)

```
User sends CTF/challenge
        ↓
Assistant solves locally in its sandbox
        ↓
Assistant writes solver script
        ↓
Assistant attempts connection to remote target from its sandbox
        ↓
If connection succeeds:
    Runs solver directly in sandbox and grabs flag
If connection fails (Network isolated):
    Calls MCP tool 'run_solver_fallback'
        ↓
MCP validates token, sandbox failure evidence, local success proof, and target allowlist
        ↓
MCP writes solver package to temporary run directory
        ↓
MCP starts isolated Docker container with strict CPU/RAM limits
        ↓
(Optional) MCP applies dynamic iptables rules to restrict container egress ONLY to target
        ↓
MCP executes solver inside container and captures stdout, stderr, hashes, and audit logs
        ↓
MCP tears down container, removes iptables rules, and compiles transcript
        ↓
Assistant verifies flag format and transcript integrity
        ↓
Assistant returns flag, proof, and execution log to User
```

---

## 2. Core Security Principles

- **No Arbitrary Commands**: Absolutely no `run_command`, `exec_shell`, or `bash` tools. The only tool that triggers execution is `run_solver_fallback`, which executes a fixed entrypoint (`solve.py` or Sage equivalent) via `subprocess(shell=False)`.
- **Mandatory Sandbox Failure Proof**: Requests are rejected unless `sandbox_failure.attempted` is `true` with a non-empty failure reason.
- **Mandatory Local Validation Summary**: Assistant must prove the solver worked against a local mockup before calling the fallback runner.
- **Strict Target Allowlist**: The destination `host:port` must be listed in `ALLOWED_TCP_TARGETS` inside `.env`.
- **IP Restrictions**: Private/local targets (like loopback, RFC1918, link-local, Google metadata) are blocked unless explicitly listed in `ALLOWED_TCP_TARGETS` for testing.
- **Resource Constraints**: Runner containers are restricted to 512MB RAM, 1 CPU, 128 PIDs, and drop all kernel capabilities.
- **Egress Firewall**: Container network traffic is restricted only to the allowed target IP and port using iptables (if `ENABLE_EGRESS_FIREWALL=true`).
- **Data Escapes Blocked**: Paths are validated to block absolute paths or directory traversals (`../`).
- **Secret Redaction**: Any auth headers, passwords, cookies, or private keys are automatically redacted from gateway and audit logs.

---

## 3. Project Structure

```
fallback-runner-mcp/
├── app/
│   ├── __init__.py
│   ├── main.py               # Server entry point
│   ├── config.py             # Environment configuration parser
│   ├── auth.py               # Token verification
│   ├── schemas.py            # Pydantic request/response models
│   ├── security.py           # Security checks (allowlist, IP blocks, bounds)
│   ├── file_package.py       # Package decoder, file limit and safety checks
│   ├── runner.py             # Execution coordinator
│   ├── docker_runner.py      # Docker lifecycle management
│   ├── egress_firewall.py    # iptables egress firewall rules
│   ├── logging_audit.py      # Auditing and secrets redaction
│   ├── transcript.py         # Structured run transcript generator
│   └── tools/
│       ├── __init__.py
│       ├── health.py         # health_check tool
│       ├── fallback.py       # run_solver_fallback tool
│       ├── runs.py           # get_run_log, list_recent_runs, delete_run tools
│       └── probe.py          # probe_target_from_runner tool
├── runner_images/
│   ├── python-ctf.Dockerfile # Python CTF image (pwntools, z3, etc.)
│   ├── python-pwn.Dockerfile  # Python PWN image
│   └── sage-ctf.Dockerfile   # Sagemath image
├── tests/                    # Unit and integration test suites
│   ├── test_auth.py
│   ├── test_security.py
│   ├── test_file_package.py
│   ├── test_runner.py
│   ├── test_logs.py
│   └── test_firewall.py
├── logs/                     # Audit trail and outputs
│   ├── gateway.log
│   └── runs/                 # Individual run folders (inputs, outputs, transcripts)
├── examples/
│   ├── solve_echo.py         # Sample pwntools solver
│   └── sample_request.json   # Reference request schema
└── scripts/
    ├── build_runner_images.sh # Image compiler
    ├── dev.sh                # Launch FastMCP dev server with local UI
    ├── test.sh               # Run unit tests
    └── cleanup_runs.sh       # Retention log scraper
```

---

## 4. Setup & Running

### Prerequisites
- Python 3.12+
- Docker installed and running
- Docker Compose (optional, for server containerization)

### Installation
1. Clone the project.
2. Initialize virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Configure the environment by copying `.env.example` to `.env` and updating the values:
   ```bash
   cp .env.example .env
   ```
   *Make sure to change `GATEWAY_TOKEN` to a long, secure random token.*

### Build Runner Docker Images
Run the script to build the runner images:
```bash
chmod +x scripts/*.sh
./scripts/build_runner_images.sh
```

### Run Tests
Execute the test suite to verify the security and orchestration constraints function correctly:
```bash
./scripts/test.sh
```

### Start Server
Run the MCP server directly using Python (standard stdio mode):
```bash
python3 -m app.main
```

Or start the server using the **FastMCP developer mode**, which launches a local dashboard at `http://localhost:5173` to test and inspect tools interactively:
```bash
./scripts/dev.sh
```

---

## 5. Integrating with ChatGPT / Assistant

ChatGPT custom connector requires an HTTPS endpoint. You can expose your local server using a tunnel:

### Expose using Cloudflare Tunnel (Automatic)
The easiest way to start both the server (in HTTP mode) and a TryCloudflare tunnel is to run the automated startup script:
```bash
./scripts/start_tunnel_server.sh
```
This script will start the server on port 8000, launch the Cloudflare Tunnel, wait for the public HTTPS URL to be generated, print it to the screen, and monitor both processes. Press `Ctrl+C` to gracefully terminate both.

### Expose using Ngrok / Cloudflare Tunnel (Manual)
If you prefer manual setup:
1. Start your MCP server in SSE mode:
   ```bash
   fastmcp run app/main.py --transport sse --port 8000
   ```
2. Open a tunnel to port 8000:
   ```bash
   ngrok http 8000
   ```
3. Copy the secure HTTPS URL pointing to the SSE route (e.g., `https://<subdomain>.ngrok-free.app/sse/`). 
   *Note: If you run with `--transport http`, use the `/mcp/` route instead (e.g., `https://<subdomain>.ngrok-free.app/mcp/`).*
4. Go to ChatGPT: **Settings** -> **Apps & Connectors** -> **Advanced settings** -> Enable **Developer Mode**.
5. Go to **Settings** -> **Connectors** -> **Create**.
6. Paste the Tunnel HTTPS URL (including the route, like `/sse/`), name it `Fallback Runner MCP`, set up static token or mixed authentication, and click **Save**.
7. Test the connection by invoking the `health_check` tool.

---

## 6. Cleanup

To prevent disk usage build-up from logs and files written for each run, you can set up a cron job or manually execute `scripts/cleanup_runs.sh`. This script will purge all runs older than the retention period set in `.env` (defaults to 7 days).
```bash
./scripts/cleanup_runs.sh
```
