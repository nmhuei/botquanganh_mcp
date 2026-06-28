# syntax=docker/dockerfile:1
# Single multi-stage CTF runner image — thay thế 4 Dockerfiles riêng lẻ
#
# Tags:
#   ctf-runner:latest      — base: Python + CTF libs + pwntools (cho python/pwn)
#   ctf-runner:web         — base + Playwright + CloakBrowser (cho web automation)
#   ctf-runner:forensics   — ubuntu + forensics tools (cho forensics)
#
# Build:
#   docker build --load -t ctf-runner:latest    --target base       -f runner_images/ctf-runner.Dockerfile .
#   docker build --load -t ctf-runner:web       --target with-web   -f runner_images/ctf-runner.Dockerfile .
#   docker build --load -t ctf-runner:forensics --target forensics  -f runner_images/ctf-runner.Dockerfile .

# ==========================
# Stage 0: Base — Python + CTF core
# ==========================
FROM python:3.12-slim AS base

# OS tools cần thiết cho CTF
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    curl \
    jq \
    file \
    git \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Python CTF libraries
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache-dir \
    pwntools \
    requests \
    pycryptodome \
    z3-solver \
    sympy \
    gmpy2 \
    libnum \
    tqdm \
    pyasn1 \
    pyasn1-modules \
    beautifulsoup4

# Runner user
RUN useradd -m -u 1000 runner
WORKDIR /work
USER runner

CMD ["python3"]

# ==========================
# Stage 1: Web — thêm Playwright + CloakBrowser
# ==========================
FROM base AS with-web

USER root
RUN pip install --no-cache-dir playwright cloakbrowser \
    && playwright install-deps chromium \
    && rm -rf /root/.cache
USER runner

RUN python3 -m cloakbrowser install

CMD ["python3"]

# ==========================
# Stage 2: Forensics — Ubuntu + forensics tools
# ==========================
FROM ubuntu:24.04 AS forensics

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    netcat-openbsd \
    curl \
    jq \
    file \
    git \
    openssl \
    binwalk \
    exiftool \
    foremost \
    steghide \
    stegseek \
    tshark \
    tcpdump \
    sleuthkit \
    yara \
    outguess \
    pngcheck \
    sox \
    ffmpeg \
    imagemagick \
    john \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir uv && \
    uv pip install --system --no-cache-dir \
    pwntools \
    requests \
    pycryptodome \
    z3-solver \
    sympy \
    gmpy2 \
    libnum \
    tqdm \
    pyasn1 \
    pyasn1-modules \
    scapy \
    volatility3 \
    oletools \
    pdfminer.six \
    python-magic \
    pyshark

RUN useradd -m -u 1000 runner
WORKDIR /work
USER runner

CMD ["python3"]
