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
port=$(.venv/bin/python - <<'PY' 2>/dev/null || printf '18427'
from dotenv import dotenv_values
print(dotenv_values('.env').get('MCP_PORT') or '18427')
PY
)

local_code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 3 "http://127.0.0.1:${port}/healthz" 2>/dev/null || printf '000')
echo "LOCAL_HEALTH=$local_code"

resolve_args=()
if getent ahosts "$host" >/dev/null 2>&1; then
    echo "DNS=RESOLVED_SYSTEM"
elif command -v dig >/dev/null 2>&1; then
    public_ip=$(dig +short +time=2 +tries=1 @1.1.1.1 "$host" A | head -n 1)
    if [ -n "$public_ip" ]; then
        echo "DNS=RESOLVED_PUBLIC_FALLBACK"
        resolve_args=(--resolve "${host}:443:${public_ip}")
    else
        echo "DNS=UNRESOLVED"
        echo "RESULT=STALE_URL_OR_CLOUDFLARE_DNS"
        exit 2
    fi
else
    echo "DNS=UNRESOLVED"
    echo "RESULT=STALE_URL_OR_CLOUDFLARE_DNS"
    exit 2
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
