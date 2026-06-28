#!/bin/bash
# Build all CTF runner images from the consolidated Dockerfile.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[*] Building CTF runner images (consolidated Dockerfile)..."
echo ""

echo "[1/2] Building base image (ctf-runner:latest)..."
docker build --load -t ctf-runner:latest -f runner_images/ctf-runner.Dockerfile --target base .

echo "[2/2] Building web image (ctf-runner:web)..."
docker build --load -t ctf-runner:web -f runner_images/ctf-runner.Dockerfile --target with-web .

echo ""
echo "[+] Done! Available tags:"
echo "    ctf-runner:latest   — Python + CTF libraries (for python/pwn)"
echo "    ctf-runner:web      — + Playwright + CloakBrowser (for web CTFs)"
echo ""
echo "    To build forensics image:"
echo "      docker build --load -t ctf-runner:forensics -f runner_images/ctf-runner.Dockerfile --target forensics ."
echo ""
echo "    SageMath image (separate, ~3GB) if needed:"
echo "      docker build --load -t ctf-sage-runner:latest -f runner_images/sage-ctf.Dockerfile ."
