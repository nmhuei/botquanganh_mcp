# MCP 502 Forensics Runbook

This runbook locates a failed MCP call before attempting a repair. Do not
restart `cloudflared`, the MCP server, or refresh ChatGPT actions while
collecting an incident's first evidence set.

## Capture and reproduce

```bash
./scripts/collect_mcp_forensics.sh
tail -F logs/gateway.log | grep --line-buffered -E 'HTTP|MCP|TOOL|AUDIT_EVENT|ERROR|WARN'
```

At the failing ChatGPT turn, record the UTC timestamp. Call `health_check` in
the affected conversation and immediately repeat it in a new conversation.
Check local origin independently:

```bash
curl -sv --connect-timeout 2 --max-time 5 http://127.0.0.1:18427/healthz
curl -sv --connect-timeout 2 --max-time 5 http://127.0.0.1:18427/api/v1/health
curl -sS http://127.0.0.1:18427/debug/transport
```

`/debug/transport` accepts direct loopback requests only and deliberately
excludes credentials, tool arguments, command output, and host paths. It
requires normal gateway authentication when `REQUIRE_AUTH=true`.

## Correlate the hop

Every HTTP response includes `X-Request-ID`. Search its value in the audit log:

```bash
grep 'bqa-REQUEST-ID' logs/gateway.log
```

The intended normal sequence is:

```text
HTTP_REQUEST_RECEIVED
MCP_MESSAGE_RECEIVED
TOOL_STARTED
TOOL_COMPLETED
MCP_MESSAGE_COMPLETED
HTTP_RESPONSE_SENT
```

`HTTP_REQUEST_RECEIVED` records safe transport attributes including `CF-Ray`,
`MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` when the client supplied
them. It never records authorization headers, tool arguments, or response
bodies. `TOOL_CATALOG_LISTED` records a deterministic SHA-256 hash of the
public `tools/list` manifest; changing hashes across identical calls signals a
local catalog instability.

| Evidence | Likely boundary |
| --- | --- |
| Local health fails | MCP process, listener, lifecycle, or local middleware |
| Local health works; public health fails | Cloudflare ingress/origin mapping |
| No local `HTTP_REQUEST_RECEIVED` and no Cloudflare event | ChatGPT connector or conversation state |
| HTTP/MCP events but no `TOOL_STARTED` | protocol parsing, routing, or catalog/schema |
| `TOOL_STARTED` without completion | tool/downstream timeout, lock, process, or resource failure |
| `HTTP_RESPONSE_SENT status=200`; ChatGPT still fails | downstream tunnel, Cloudflare, or connector runtime |

If an affected chat fails while a new chat succeeds and no HTTP event arrives
for the affected call, treat it as strong evidence of per-conversation
connector state. Preserve the correlation timestamps and use a new conversation
as the operational workaround.

## Safe checks

```bash
ss -lntp | grep ':18427'
ps aux | grep -E 'fastmcp|botquanganh|18427' | grep -v grep
ps aux | grep cloudflared | grep -v grep
grep -R '18427\|localhost\|127.0.0.1' ~/.cloudflared . 2>/dev/null
```

When the public hostname is known, compare it with local origin without
restarting anything:

```bash
curl -sv --connect-timeout 5 --max-time 10 https://YOUR-MCP-DOMAIN/healthz
```

Do not use `bqa stop` during this workflow: it is a full lifecycle operation
and can stop the tunnel. A server-only restart is a later remediation step only
after tests pass and an incident patch/rollback bundle is saved.
