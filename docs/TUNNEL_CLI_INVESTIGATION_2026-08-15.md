# Tunnel CLI Investigation — 2026-08-15

## Root cause

There is no separate working CLI implementation and broken direct-script
implementation in the current tree. `bqa start` and bare `bqa` both call
`app.cli.lifecycle.start()`, which executes `run_mcp_tunnel.sh start` from the
repository root. The first divergence is output post-processing after that shared
backend returns, not tunnel creation.

The reproduced failure during the port-18427 cutover was local DNS negative caching:

- cloudflared PID `752041` generated the current URL at `13:34:00Z`;
- the same PID registered its connection at `13:34:01Z`;
- FastMCP was healthy on `127.0.0.1:18427`;
- the system resolver returned no record for the new hostname;
- public resolvers `1.1.1.1` and `8.8.8.8` returned Cloudflare addresses;
- public `/healthz` and MCP initialize both returned HTTP 200 when tested with the
  public answer via `curl --resolve`.

The readiness gate correctly withheld `tunnel_url.txt`, so neither the script nor the
CLI advertised an unverified endpoint. DNS fallback was then added to the cold-start
readiness and diagnostic paths. The currently running supervisor predated that patch,
so the already-verified URL was atomically published once during the authorized port
migration; future cold starts load the fallback automatically.

## Entry-point call graph

| Entry point | Final shell/script | Waits for health? | URL source | Appends `/mcp`? |
|---|---|---|---|---|
| `./run_mcp_tunnel.sh start` | `scripts/start_tunnel_server.sh` | Yes: current URL, registration, local and public health | `logs/tunnel_url.txt` after atomic publication | Yes |
| `bqa start` | `run_mcp_tunnel.sh start` through `lifecycle.start()` | Same backend wait | canonical file, then CLI rendering | Yes |
| bare `bqa` | `lifecycle.start()` → `run_mcp_tunnel.sh start` | Same backend wait plus status validation | canonical file through `status_data()` | Yes |
| `bqa restart` | `scripts/restart_server_only.sh` | Waits for the replacement listener | Existing canonical file | Yes |
| `bqa server restart` | `scripts/restart_server_only.sh` | Same implementation | Existing canonical file | Yes |
| `bqa url` | No lifecycle script | n/a; requires `connector_ready` | `logs/tunnel_url.txt` | Yes |

## URL trace

```text
cloudflared PID 752041
  -> logs/cloudflared.log: sponsored-observed-earn-exemption.trycloudflare.com
  -> current-generation byte-offset parser
  -> registration + local/public readiness
  -> atomic logs/tunnel_url.txt: https://HOST
  -> run_mcp_tunnel.sh connector_url(): https://HOST/mcp
  -> lifecycle.connector_url(): https://HOST/mcp
  -> CLI renderer: https://HOST/mcp
```

The canonical file intentionally stores the base URL. Both public user-facing paths
append exactly one `/mcp`; no formatting divergence exists.

## URL semantics

| Probe | Result |
|---|---|
| `GET https://HOST` | HTTP 404 — expected, no root route |
| `GET https://HOST/` | HTTP 404 — expected |
| `GET https://HOST/healthz` | HTTP 200 `OK` |
| `GET https://HOST/mcp` | HTTP 405 — expected because MCP initialize is POST |
| `POST https://HOST/mcp` initialize | HTTP 200 with MCP initialize result |

Browser behavior at the base URL is therefore not a connector-readiness signal.

## Environment comparison

| Checkpoint | Direct script | CLI | Different? |
|---|---|---|---|
| cwd/repo root | Script immediately `cd`s to its own repository root | `run_script()` sets cwd to repo root | No |
| `.env` | Reads repository `.env` | Loads the same repository `.env` | No |
| origin | `127.0.0.1:18427` | Same backend | No |
| cloudflared | Resolved from inherited `PATH` | Same inherited environment | No |
| log directory | repository `logs/` | Same | No |
| URL generation | supervisor-owned cloudflared PID | Same PID | No |
| registration/public health | supervisor gate | Same backend gate | No |
| returned path | `/mcp` | `/mcp` | No |
| process lifetime | nohup supervisor survives caller | CLI waits for script; same supervisor survives | No |

## Timing and ownership

The supervisor is re-parented under user systemd after the launcher exits and owns both
FastMCP and cloudflared. There is no `EXIT` cleanup trap in the start path. Only
`TERM`/`INT` invoke intentional shutdown. Returning from the direct script does not
terminate cloudflared.

Publication order is enforced as:

```text
spawn -> current-generation URL -> registered connection -> local health
      -> public health -> atomic canonical file -> shell output -> CLI output
```

## Hypothesis results

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1 URL formatting mismatch | Rejected | Shell and CLI both return the same `https://HOST/mcp` value |
| H2 readiness race | Fixed historically; rejected currently | Publication is after registration and health gates |
| H3 stale generation | Rejected | Byte-offset parser regression passes; old log URL is ignored |
| H4 environment/cwd difference | Rejected | Both paths normalize to the same repo, `.env`, port and logs |
| H5 parent/process lifetime | Rejected | nohup supervisor persists under user systemd; no EXIT cleanup |
| H6 auth/transport difference | Rejected | `/healthz` and MCP initialize both return 200 |
| Local DNS negative cache | Confirmed for reproduced cutover delay | System lookup failed while two public resolvers and `curl --resolve` succeeded |

## Script audit

`run_mcp_tunnel.sh` consumers include:

- `app/cli/lifecycle.py` for start and stop;
- `scripts/quality_gate.sh` and isolated lifecycle tests;
- `scripts/collect_diagnostics.sh`;
- README and operator documentation.

Verdict: **KEEP as a thin compatibility/lifecycle wrapper**. It does not satisfy the
zero-consumer deletion gate.

## Live safety

```text
Tunnel PID before: 752041
URL before: https://sponsored-observed-earn-exemption.trycloudflare.com
Live tunnel touched during this investigation: NO
Tunnel PID after: 752041
URL after: https://sponsored-observed-earn-exemption.trycloudflare.com
Supervisor PID before/after: 751983 / 751983
Server PID before/after: 752029 / 752029
```

All five final connector probes returned `CONNECTOR_READY`; live invariants passed.
