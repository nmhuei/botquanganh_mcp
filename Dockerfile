# syntax=docker/dockerfile:1
# Multi-stage build: lấy docker CLI từ image chính thức, Python app riêng biệt
FROM docker:28-cli AS docker-cli

FROM python:3.12-slim

# Copy docker CLI binary — không cần docker.io full stack
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
COPY requirements.txt .

# Install uv + dependencies
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache-dir -r requirements.txt

# Copy ứng dụng
COPY . .

EXPOSE 8000
ENV PYTHONPATH=/app
CMD ["python3", "-m", "app.main"]
