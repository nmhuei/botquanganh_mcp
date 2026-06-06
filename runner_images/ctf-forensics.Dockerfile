FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV UV_BREAK_SYSTEM_PACKAGES=1

RUN sed -i 's/archive.ubuntu.com/vn.archive.ubuntu.com/g' /etc/apt/sources.list.d/ubuntu.sources && \
    apt-get update && apt-get install -y \
    binwalk \
    exiftool \
    foremost \
    steghide \
    tshark \
    tcpdump \
    wireshark-common \
    john \
    qemu-user-static \
    strace \
    ltrace \
    p7zip-full \
    unrar \
    bzip2 \
    xz-utils \
    zstd \
    imagemagick \
    ffmpeg \
    file \
    xxd \
    binutils \
    sqlite3 \
    zbar-tools \
    python3-pip \
    python3-dev \
    outguess \
    pngcheck \
    sox \
    ruby \
    ruby-dev \
    scalpel \
    sleuthkit \
    yara \
    fcrackzip \
    cabextract \
    libmagic1 \
    libmagic-dev \
    libffi-dev \
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

RUN wget https://github.com/RickdeJager/stegseek/releases/download/v0.6/stegseek_0.6-1.deb && \
    apt-get update && apt-get install -y ./stegseek_0.6-1.deb poppler-utils tesseract-ocr tesseract-ocr-eng && \
    rm stegseek_0.6-1.deb && \
    rm -rf /var/lib/apt/lists/*

RUN gem install --no-document zsteg

RUN pip3 install --no-cache-dir --break-system-packages uv && \
    uv pip install --system --no-cache-dir \
    stegoveritas \
    scapy \
    volatility3 \
    pillow \
    numpy \
    pycryptodome \
    oletools \
    pdfminer.six \
    python-magic \
    pyshark \
    yara-python

RUN stegoveritas_setup || python3 -m stegoveritas --setup || true

RUN mkdir -p /opt/wordlists && \
    printf '%s\n' password 123456 123456789 qwerty abc123 letmein admin welcome > /opt/wordlists/basic.txt

RUN getent group wireshark || groupadd wireshark && \
    useradd -m -o -u 1000 runner && \
    usermod -aG wireshark runner
WORKDIR /work
USER runner
CMD ["bash"]
