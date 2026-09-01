#!/usr/bin/env bash
set -euo pipefail

have_font() {
    local wanted="$1"
    local matched
    matched="$(fc-match -f '%{family}\n' "$wanted" 2>/dev/null || true)"
    case "$matched" in
        *"$wanted"*) return 0 ;;
        *) return 1 ;;
    esac
}

if ! command -v fc-list >/dev/null 2>&1; then
    echo "[!] fontconfig is unavailable; BQA Center will use the Qt system font fallback."
    exit 0
fi

if have_font "Noto Sans" && have_font "Noto Sans Mono"; then
    echo "[+] UI fonts available: Noto Sans + Noto Sans Mono"
    exit 0
fi

if [ "${BQA_SKIP_FONT_INSTALL:-0}" = "1" ]; then
    echo "[!] Noto UI fonts are missing and BQA_SKIP_FONT_INSTALL=1; using system fallback."
    exit 0
fi

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        return 127
    fi
}

echo "[*] Installing cross-distro Noto UI fonts for BQA Center..."
installed=0
if command -v apt-get >/dev/null 2>&1; then
    if run_privileged apt-get update -qq \
        && run_privileged apt-get install -y fonts-noto-core fonts-noto-mono; then
        installed=1
    fi
elif command -v dnf >/dev/null 2>&1; then
    if run_privileged dnf install -y google-noto-sans-fonts google-noto-sans-mono-fonts; then
        installed=1
    fi
elif command -v pacman >/dev/null 2>&1; then
    if run_privileged pacman -S --needed --noconfirm noto-fonts; then
        installed=1
    fi
fi

if [ "$installed" -eq 1 ]; then
    command -v fc-cache >/dev/null 2>&1 && fc-cache -f >/dev/null 2>&1 || true
fi

if have_font "Noto Sans" && have_font "Noto Sans Mono"; then
    echo "[+] Installed UI fonts: Noto Sans + Noto Sans Mono"
else
    echo "[!] Could not install Noto automatically. BQA Center will use the Qt system font fallback." >&2
    echo "    Debian/Kali/Ubuntu: fonts-noto-core fonts-noto-mono" >&2
    echo "    Fedora: google-noto-sans-fonts google-noto-sans-mono-fonts" >&2
    echo "    Arch: noto-fonts" >&2
fi
