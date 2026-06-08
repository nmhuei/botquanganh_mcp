#!/usr/bin/env bash
# CTF Harness — New Challenge Workspace Setup
# Usage: ./scripts/new-challenge.sh <name> <category> [host] [port]
set -euo pipefail

NAME="${1:?Usage: $0 <name> <category> [host] [port]}"
CATEGORY_RAW="${2:?Provide category: pwn|crypto|web|reverse|rev|forensics|misc|osint|ai-ml|cloud-ci}"
HOST="${3:-}"
PORT="${4:-}"

case "$CATEGORY_RAW" in
  rev) CATEGORY="reverse" ;;
  *)   CATEGORY="$CATEGORY_RAW" ;;
esac
case "$CATEGORY" in
  pwn|crypto|web|reverse|forensics|misc|osint|ai-ml|cloud-ci) ;;
  *) echo "[-] unsupported category: $CATEGORY_RAW"; exit 2 ;;
esac

HARNESS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="$HARNESS_ROOT/workspaces/$NAME"
WS_REL="workspaces/$NAME"
mkdir -p "$WS"/{artifacts,exploit/attempts,recon,notes,evidence,payloads,transcripts,tmp,logs,proofs,reports}

TMPL="$HARNESS_ROOT/templates/$CATEGORY/solve.py"
[[ -f "$TMPL" ]] || TMPL="$HARNESS_ROOT/templates/misc/solve.py"
sed "s/__CHALLENGE__/$NAME/g; s/__HOST__/$HOST/g; s/__PORT__/${PORT:-TARGET_PORT}/g" "$TMPL" > "$WS/exploit/solve.py"
chmod +x "$WS/exploit/solve.py"

cat > "$WS/state.json" <<STATE
{
  "challenge": "$NAME",
  "category": "$CATEGORY",
  "remote": { "host": "$HOST", "port": "$PORT" },
  "phase": "triage",
  "hypotheses": [],
  "confirmed_primitives": [],
  "attempts": 0,
  "flag": null,
  "flag_verified": false,
  "blocker": null,
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
STATE

cat > "$WS/notes/NOTES.md" <<NOTES
# $NAME — $(echo "$CATEGORY" | tr '[:lower:]' '[:upper:]')

## Challenge Description

## Files

## Triage

## Recon

## Hypotheses
1.

## Attempts

## Working Exploit

## Verification

## Flag
\`\`\`
\`\`\`
NOTES

if [[ "$CATEGORY" == "pwn" || "$CATEGORY" == "reverse" ]]; then
cat > "$WS/recon/recon.sh" <<'RECON'
#!/usr/bin/env bash
set -euo pipefail
WS="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$WS/recon/results.txt"
echo "=== RECON $(date) ===" | tee "$OUT"
for bin in "$WS"/artifacts/*; do
  [[ -f "$bin" ]] || continue
  echo "" | tee -a "$OUT"
  echo "===== FILE: $bin =====" | tee -a "$OUT"
  file "$bin" | tee -a "$OUT" || true
  checksec --file="$bin" 2>/dev/null | tee -a "$OUT" || true
  strings -a "$bin" | grep -iE 'flag|ctf|sh|/bin|system|execve|gets|scanf|printf|password|correct|wrong' | head -200 | tee -a "$OUT" || true
  readelf -s "$bin" 2>/dev/null | head -100 | tee -a "$OUT" || true
  ldd "$bin" 2>/dev/null | tee -a "$OUT" || true
done
sha256sum "$WS"/artifacts/* 2>/dev/null | tee "$WS/evidence/input-sha256.txt" || true
echo "Results saved: $OUT"
RECON
chmod +x "$WS/recon/recon.sh"
fi

REMOTE_TARGET="https://target.ctf.example"
REMOTE_URL="https://target.ctf.example"
if [[ -n "$HOST" ]]; then
  REMOTE_TARGET="$HOST${PORT:+:$PORT}"
  if [[ "$PORT" == "443" ]]; then
    REMOTE_URL="https://$HOST"
  elif [[ -n "$PORT" ]]; then
    REMOTE_URL="http://$HOST:$PORT"
  else
    REMOTE_URL="http://$HOST"
  fi
fi

cat > "$WS/ctf.yaml" <<YAML
challenge:
  name: $NAME
  category: $CATEGORY
  workspace: workspaces
  flag_regex: '(?i)(?:FLAG|CTF|picoCTF|HTB|DUCTF|SEKAI|idekCTF|ictf|TBTL|KCSC|GPNCTF|THCON|1337UP|L3AK|n00bz)\{[^}\r\n]{4,300}\}'

policy:
  local_first: true
  require_remote_evidence: true
  reject_decoy_words: [fake, dummy, test, local, example, placeholder]
  authorized_remote_domains:
    - localhost
    - 127.0.0.1
    - ctf.kitctf.de
${HOST:+    - $HOST
}
local:
  build: []
  start: []
  smoke: []
  stop: []

solver:
  local: 'python3 $WS_REL/exploit/solve.py'
  remote: 'REMOTE_URL="$REMOTE_URL" HOST="$HOST" PORT="$PORT" python3 $WS_REL/exploit/solve.py REMOTE'

remote:
  target: '$REMOTE_TARGET'
  env:
    REMOTE_URL: '$REMOTE_URL'
    HOST: '$HOST'
    PORT: '$PORT'

proof:
  # Replace with a real CTFd/checker command to upgrade candidate -> verified.
  command: ''
YAML

cat > "$WS/recon/README.md" <<EOF2
# Recon

Run category-specific recon here. For pwn/reverse, use:

\`\`\`bash
bash $WS_REL/recon/recon.sh
\`\`\`
EOF2

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  CTF Harness — Challenge Ready       ║"
echo "╠══════════════════════════════════════╣"
printf "║  Name     : %-26s║\n" "$NAME"
printf "║  Category : %-26s║\n" "$CATEGORY"
[[ -n "$HOST" ]] && printf "║  Remote   : %-26s║\n" "$REMOTE_TARGET"
printf "║  Workspace: %-26s║\n" "$WS_REL/"
echo "╚══════════════════════════════════════╝"
echo "Next: copy files to $WS_REL/artifacts/ ; edit $WS_REL/exploit/solve.py"
echo "Run: ctfh --config $WS_REL/ctf.yaml check"
