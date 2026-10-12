# BotQuangAnh Host MCP

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/nmhuei/botquanganh_mcp)
[![Tests](https://img.shields.io/badge/tests-790%20passed-success.svg)](https://github.com/nmhuei/botquanganh_mcp)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-informational.svg)](https://python.org)
[![Rust](https://img.shields.io/badge/desktop-Rust%20%2B%20WebKitGTK-orange.svg)](https://rust-lang.org)
[![FastMCP](https://img.shields.io/badge/fastmcp-3.4.7-purple.svg)](https://github.com/jlowin/fastmcp)

BotQuangAnh Host MCP is a secure Model Context Protocol (MCP) host runtime and native desktop studio.
It connects AI models to local host environments with capability gating, chat workspace isolation, and full audit logging.

---

## Key Capabilities

- **MCP 2.0 Super-Tools:** Consolidates all host operations into eight high-performance tools.
- **Pre-bind Capability Gating:** Requires explicit chat binding before any workspace access.
- **Isolated Chat Workspaces:** Allocates dedicated directories with storage quotas and auto-sweeping.
- **Guarded Command Execution:** Runs shell commands safely with timeouts, process supervision, and async task handoff.
- **Stateless HTTP Transport:** Prevents connection drops and session conflicts over Cloudflare tunnels.
- **Native Rust Studio:** Delivers a lightweight desktop interface using Rust, WebKitGTK, and 0 MB browser RAM bloat.

---

## MCP 2.0 Super-Tools

BQA MCP 2.0 provides eight structured tools:

| Tool | Action / Parameters | Description |
|---|---|---|
| `server_info` | *(none)* | Returns server health, limits, and the active tool catalog. |
| `workspace_context` | `action`, `chat_id`, `state`, `note` | Binds sessions, updates `STATE.md`, and tracks hypotheses. |
| `workspace_explore` | `action`, `path`, `lines` | Lists directory trees or reads file content with sliding line windows. |
| `workspace_edit` | `action`, `path`, `text`, `old`, `new` | Writes, appends, or replaces file content with atomic safeguards. |
| `workspace_search` | `pattern`, `path`, `type`, `max_results` | Searches text, regex, or paths with strict payload budgeting. |
| `terminal_execute` | `command`, `timeout_seconds`, `cwd` | Executes shell commands with adaptive task handoff for long runs. |
| `task` | `action`, `task_id`, `input` | Manages background tasks (`list`, `tail`, `wait`, `kill`, `input`). |
| `web_intelligence` | `url`, `max_bytes`, `extract_mode` | Fetches web data with size limits and extracts structured text. |

---

## Installation

### Prerequisites

- Linux (Ubuntu, Debian, Fedora, Arch)
- Python >= 3.10 and `uv`
- Optional for Native Desktop: Rust toolchain, `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`

### Automated Install

Run the official installer script:

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

The installer configures virtual environment `.venv`, builds native desktop binaries if Rust is available, generates `.env`, and links `bqa` into `~/.local/bin/`.

---

## Essential Commands

### 1. Service Lifecycle

```bash
bqa start              # Start runtime: server, tunnel, bridge, and print connector URL
bqa stop               # Stop all background services
bqa restart            # Restart MCP server while keeping active tunnel URL
bqa status             # Show current runtime status and health
bqa url                # Display active connector URL
```

### 2. User Interfaces

```bash
bqa ui                 # Launch BQA Native Studio (Rust Desktop)
bqa ui --classic       # Launch fallback Tkinter interface
bqa tui                # Launch terminal UI for headless or SSH sessions
```

### 3. Session and Workspace Operations

```bash
bqa session list       # List recent agent sessions
bqa session new        # Create and bind a new session
bqa chats list         # List active chat workspaces
bqa chats show <id>    # Display workspace path and STATE.md details
bqa chats prune        # Clean expired workspaces
```

### 4. Diagnostics and Logs

```bash
bqa doctor             # Run environment diagnostics and public tunnel checks
bqa logs all -f        # Stream unified logs (server, tunnel, launcher, audit)
```

---

## Key Configuration

All settings reside in `.env`. Core parameters include:

| Parameter | Default | Purpose |
|---|---|---|
| `MCP_PORT` | `18427` | Local bridge TCP port. |
| `ATTRIBUTION_MODE` | `enforce` | Enforces chat binding before file and command access. |
| `HOST_WORKSPACE_DIR` | `~` | Root directory accessible by tools. |
| `HOST_COMMAND_POLICY` | `guarded` | Blocks destructive shell commands and fork bombs. |
| `HOST_CHAT_WORKSPACES` | `true` | Enables isolated directories for individual chat IDs. |
| `HOST_CHAT_ROOT` | `~/Downloads/bqa-workspaces` | Storage path for isolated chat workspaces. |
| `HOST_CHAT_QUOTA_MB` | `2048` | Maximum storage quota per workspace (in MB). |
| `MAX_TIMEOUT_SECONDS` | `300` | Maximum allowed command execution duration. |

---

## Verification

Run the test suite using `pytest`:

```bash
.venv/bin/pytest -q
```

All 790 integration, regression, and stress tests pass with full assertion coverage.

---

## License

MIT License. See [SECURITY.md](SECURITY.md) for vulnerability disclosure policies.
