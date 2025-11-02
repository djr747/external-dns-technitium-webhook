# Multi-stage build with Chainguard Python for minimal attack surface and daily security updates
# Chainguard images: ultra-minimal, zero CVEs, updated daily, SLSA Level 3 provenance
# Use -dev variant for builder (includes pip, build tools), minimal runtime for final stage
FROM cgr.dev/chainguard/python:latest-dev AS builder

# Set working directory
WORKDIR /build

# Copy only requirements for better layer caching
COPY pyproject.toml ./

# Install dependencies (production only, no dev deps)
# Chainguard images have no shell - use exec form (JSON array) for RUN
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "--upgrade", "pip", "setuptools", "wheel"]
RUN ["python", "-m", "pip", "install", "--no-cache-dir", "."]

# Final stage - Chainguard Python (minimal runtime, non-root by default)
FROM cgr.dev/chainguard/python:latest

LABEL org.opencontainers.image.title="ExternalDNS Technitium Webhook" \
      org.opencontainers.image.description="ExternalDNS webhook provider for Technitium DNS Server" \
      org.opencontainers.image.source="https://github.com/djr747/external-dns-technitium-webhook" \
      org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.vendor="Chainguard" \
    org.opencontainers.image.base.name="cgr.dev/chainguard/python:latest"

# Chainguard images run as non-root (UID 65532) by default - no need to create user

# Copy installed packages from builder
# Use numeric UID:GID (65532:65532) for Kubernetes runAsNonRoot compliance
# Chainguard Python uses /home/nonroot/.local for user site-packages
COPY --from=builder --chown=65532:65532 /home/nonroot/.local /home/nonroot/.local

# Set environment variables
ENV PATH="/home/nonroot/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    LISTEN_ADDRESS="0.0.0.0"

# Copy application code
WORKDIR /app
COPY --chown=65532:65532 external_dns_technitium_webhook ./external_dns_technitium_webhook

# Chainguard images are already non-root (UID 65532); use numeric UID for Kubernetes runAsNonRoot compliance
USER 65532

# Health check
# Chainguard images have no shell - use exec form with python
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"]

# Expose ports
EXPOSE 8888 8080

# Run the application
# Using --ws websockets-sansio to avoid deprecated websockets.legacy implementation
# This ensures compatibility with latest websockets library (v14.0+)
CMD ["python", "-m", "uvicorn", "external_dns_technitium_webhook.main:app", "--host", "0.0.0.0", "--port", "8888", "--no-access-log", "--ws", "websockets-sansio"]
