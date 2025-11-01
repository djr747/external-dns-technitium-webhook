# Multi-stage build with Chainguard Python for minimal attack surface and daily security updates
# Chainguard images: ultra-minimal, zero CVEs, updated daily, SLSA Level 3 provenance
FROM chainguard/python:latest-dev AS builder

# Set working directory
WORKDIR /build

# Copy only requirements for better layer caching
COPY pyproject.toml ./

# Install dependencies (production only, no dev deps)
# Chainguard's dev variant includes pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Final stage - Chainguard Python (minimal runtime, non-root by default)
FROM chainguard/python:latest

LABEL org.opencontainers.image.title="ExternalDNS Technitium Webhook" \
      org.opencontainers.image.description="ExternalDNS webhook provider for Technitium DNS Server" \
      org.opencontainers.image.source="https://github.com/djr747/external-dns-technitium-webhook" \
      org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.vendor="Chainguard" \
    org.opencontainers.image.base.name="cgr.dev/chainguard/python:latest"

# Chainguard images run as non-root (UID 65532) by default - no need to create user

# Copy installed packages from builder
# Chainguard Python uses /home/nonroot/.local for user site-packages
COPY --from=builder --chown=nonroot:nonroot /home/nonroot/.local /home/nonroot/.local

# Set environment variables
ENV PATH="/home/nonroot/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    LISTEN_ADDRESS="0.0.0.0" \
    LISTEN_PORT="8888"

# Copy application code
WORKDIR /app
COPY --chown=nonroot:nonroot external_dns_technitium_webhook ./external_dns_technitium_webhook

# Chainguard images are already non-root, but explicit is better
USER nonroot

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8888/health', timeout=3)" || exit 1

# Expose port
EXPOSE 8888

# Run the application
CMD ["python", "-m", "uvicorn", "external_dns_technitium_webhook.main:app", "--host", "0.0.0.0", "--port", "8888", "--no-access-log"]
