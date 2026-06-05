FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    socat \
    file \
    binutils \
    patchelf \
    gdb \
    gdbserver \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache-dir \
    pwntools \
    requests \
    pycryptodome \
    z3-solver \
    sympy \
    gmpy2 \
    playwright \
    cloakbrowser \
    libnum \
    tqdm \
    pyasn1 \
    pyasn1-modules

RUN git clone --depth 1 https://github.com/pwndbg/pwndbg /opt/pwndbg && \
    uv pip install --system --no-cache-dir /opt/pwndbg

RUN playwright install-deps chromium

RUN useradd -m -u 1000 runner
WORKDIR /work
USER runner

RUN echo "source /opt/pwndbg/gdbinit.py" > /home/runner/.gdbinit

RUN python3 -m cloakbrowser install

CMD ["python3"]

