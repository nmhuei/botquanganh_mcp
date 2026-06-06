FROM sagemath/sagemath:latest

# Sagemath container typically runs as user 'sage'.
# We can install extra Python packages inside Sagemath's env if needed.
USER root
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    netcat-openbsd \
    ncat \
    nmap \
    socat \
    jq \
    dnsutils \
    openssl \
    iputils-ping \
    git \
    && rm -rf /var/lib/apt/lists/*

USER sage
WORKDIR /work

RUN sage -pip install --no-cache-dir \
    pycryptodome \
    z3-solver \
    libnum \
    tqdm \
    pyasn1 \
    pyasn1-modules

CMD ["sage"]
