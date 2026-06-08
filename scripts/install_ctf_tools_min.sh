#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
LOG_DIR="${HOME}/.ctf-tools"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/min-install-$(date +%Y-%m-%d_%H%M%S).log"

log(){ echo "==> $*" | tee -a "$LOG_FILE"; }

install_python(){
  python3 -m pip install --upgrade pip >>"$LOG_FILE" 2>&1 || true
  python3 -m pip install \
    pwntools requests pycryptodome z3-solver PyYAML beautifulsoup4 \
    capstone ropper ROPGadget angr frida-tools qiling \
    >>"$LOG_FILE" 2>&1 || true
}

install_apt(){
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update >>"$LOG_FILE" 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
      gdb radare2 binutils binwalk foremost libimage-exiftool-perl \
      tshark tcpdump strace ltrace curl jq nmap whois dnsutils \
      netcat-openbsd ncat socat qemu-user qemu-system-x86 qrencode \
      >>"$LOG_FILE" 2>&1 || true
  else
    log "apt-get not found; skipping apt packages"
  fi
}

verify(){
  for c in python3 curl jq nc ncat gdb file strings; do
    if command -v "$c" >/dev/null 2>&1; then log "OK $c=$(command -v "$c")"; else log "MISSING $c"; fi
  done
  python3 - <<'PY' || true
mods = ['pwn','requests','Crypto','z3','yaml']
for m in mods:
    try:
        __import__(m); print('OK', m)
    except Exception as e:
        print('MISSING', m, e)
PY
}

case "$MODE" in
  python) install_python ;;
  apt) install_apt ;;
  verify|--verify) verify ;;
  all) install_apt; install_python; verify ;;
  *) echo "Usage: $0 [all|python|apt|verify]" >&2; exit 2 ;;
esac
log "log saved: $LOG_FILE"
