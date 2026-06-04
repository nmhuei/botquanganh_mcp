#!/bin/bash
# Exit immediately if any command fails
set -e

# Change directory to the root of the project (parent of scripts/)
cd "$(dirname "$0")/.."

echo "[*] Building python-ctf runner image (ctf-python-runner:latest)..."
docker build --load -t ctf-python-runner:latest -f runner_images/python-ctf.Dockerfile .

echo "[*] Building python-pwn runner image (ctf-pwn-runner:latest)..."
docker build --load -t ctf-pwn-runner:latest -f runner_images/python-pwn.Dockerfile .

echo "[*] Building sage-ctf runner image (ctf-sage-runner:latest)..."
docker build --load -t ctf-sage-runner:latest -f runner_images/sage-ctf.Dockerfile .


echo "[+] All runner images successfully built!"
