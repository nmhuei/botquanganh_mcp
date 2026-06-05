FROM python:3.12-slim

# Install docker CLI, iptables, and sudo (required for managing docker containers and rules from inside this server)
RUN apt-get update && apt-get install -y \
    docker.io \
    iptables \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Grant passwordless sudo privilege specifically for iptables commands
RUN echo "mcp ALL=(ALL) NOPASSWD: /usr/sbin/iptables" >> /etc/sudoers

# Create runner user
RUN useradd -m -u 1000 mcp && usermod -aG sudo mcp

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R mcp:mcp /app

# Run as mcp user
USER mcp

EXPOSE 8000
ENV PYTHONPATH=/app
CMD ["python3", "-m", "app.main"]
