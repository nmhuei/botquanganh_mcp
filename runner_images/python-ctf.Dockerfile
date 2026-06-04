FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    socat \
    file \
    binutils \
    patchelf \
    gdb \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pwntools \
    requests \
    pycryptodome \
    z3-solver \
    sympy \
    gmpy2

RUN useradd -m -u 1000 runner
WORKDIR /work
USER runner

CMD ["python3"]
