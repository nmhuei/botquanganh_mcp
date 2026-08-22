#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

URL_FILE="logs/tunnel_url.txt"
base_url=$(head -n 1 "$URL_FILE" 2>/dev/null | sed 's:/*$::')
if [[ ! "$base_url" =~ ^https://[a-zA-Z0-9-]+\.trycloudflare\.com$ ]]; then
    echo "RESULT=NO_URL"
    exit 1
fi
host=${base_url#https://}
port="${MCP_PORT:-}"
if [ -z "$port" ] && [ -f .env ]; then
    port=$(grep -E "^[[:space:]]*MCP_PORT=" .env 2>/dev/null | tail -n 1 | sed -E "s/^[[:space:]]*MCP_PORT=[[:space:]]*//; s/[\x27\"]//g; s/[[:space:]]*$//" || true)
fi
port="${port:-18427}"

local_code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 3 "http://127.0.0.1:${port}/healthz" 2>/dev/null || printf '000')
echo "LOCAL_HEALTH=$local_code"

resolve_args=()
if getent ahosts "$host" >/dev/null 2>&1; then
    echo "DNS=RESOLVED_SYSTEM"
elif command -v dig >/dev/null 2>&1 && public_ip=$(dig +short +time=1 +tries=1 @1.1.1.1 "$host" A 2>/dev/null | head -n 1) && [ -n "$public_ip" ]; then
    echo "DNS=RESOLVED_PUBLIC_FALLBACK"
    resolve_args=(--resolve "${host}:443:${public_ip}")
else
    public_ip=$(tail -n 50 logs/cloudflared.log 2>/dev/null | grep -o -E 'ip=[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | tail -n 1 | cut -d= -f2 || true)
    [ -n "$public_ip" ] || public_ip=$(getent ahostsv4 trycloudflare.com 2>/dev/null | awk '{print $1}' | head -n 1 || true)
    [ -n "$public_ip" ] || public_ip="104.16.230.132"
    echo "DNS=RESOLVED_CLOUDFLARE_EDGE"
    resolve_args=(--resolve "${host}:443:${public_ip}")
fi

public_response=$(curl --silent --show-error --write-out $'\n%{http_code}' \
    --max-time 8 "${resolve_args[@]}" "$base_url/healthz" 2>/dev/null || printf '\n000')
public_code=${public_response##*$'\n'}
public_body=${public_response%$'\n'*}
echo "PUBLIC_HEALTH=$public_code"
if [[ "$public_body" == *"1033"* ]]; then
    echo "RESULT=CLOUDFLARED_UNHEALTHY"
    exit 3
fi
case "$public_code" in
    502) echo "RESULT=ORIGIN_UNREACHABLE"; exit 4 ;;
    200) ;;
    *) echo "RESULT=PUBLIC_HEALTH_FAILED"; exit 5 ;;
esac

headers=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream')
if [ -n "${GATEWAY_TOKEN:-}" ]; then
    headers+=(-H "Authorization: Bearer ${GATEWAY_TOKEN}")
fi
mcp_code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 10 "${headers[@]}" \
    "${resolve_args[@]}" \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"bqa-diagnostic","version":"1"}}}' \
    "$base_url/mcp" 2>/dev/null || printf '000')
echo "MCP_INITIALIZE=$mcp_code"
if [ "$mcp_code" = 200 ]; then
    echo "RESULT=CONNECTOR_READY"
    exit 0
fi
echo "RESULT=MCP_TRANSPORT_OR_AUTH_FAILED"
exit 6
