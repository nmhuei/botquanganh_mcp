FROM sagemath/sagemath:latest

# Sagemath container typically runs as user 'sage'.
# We can install extra Python packages inside Sagemath's env if needed.
USER root
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    socat \
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

