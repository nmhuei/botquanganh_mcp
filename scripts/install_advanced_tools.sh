#!/bin/bash
set -e

cd "$(dirname "$0")/.."

./scripts/install_basic.sh

echo "[*] Building advanced Docker runner images..."
./scripts/build_runner_images.sh

if grep -q '^ENABLE_ADVANCED_TOOLS=' .env; then
    sed -i 's/^ENABLE_ADVANCED_TOOLS=.*/ENABLE_ADVANCED_TOOLS=true/' .env
else
    printf '\nENABLE_ADVANCED_TOOLS=true\n' >> .env
fi

echo "[+] Advanced tools installed and enabled in .env."
echo "[+] Restart the MCP server to expose runner/probe/shell tools."
