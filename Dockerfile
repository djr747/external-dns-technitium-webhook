# Multi-stage build with Red Hat UBI10 for enterprise support and CVE remediation
# Using ubi10/ubi-minimal as base and installing Python 3.12 from AppStream
FROM registry.access.redhat.com/ubi10/ubi-minimal:latest AS builder

# Install Python 3.12 and build tools
RUN microdnf update -y && \
    microdnf install -y python3.12 python3.12-pip python3.12-devel gcc && \
    microdnf clean all && \
    rm -rf /var/cache/yum

# Ensure python3.12 is the default python
RUN ln -sf /usr/bin/python3.12 /usr/bin/python && \
    ln -sf /usr/bin/pip3.12 /usr/bin/pip

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only requirements for better layer caching
WORKDIR /build
COPY pyproject.toml ./

# Install dependencies (production only, no dev deps)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Final stage - Red Hat UBI 10 Minimal (smaller, still enterprise supported)
FROM registry.access.redhat.com/ubi10/ubi-minimal:latest

LABEL org.opencontainers.image.title="ExternalDNS Technitium Webhook" \
      org.opencontainers.image.description="ExternalDNS webhook provider for Technitium DNS Server" \
      org.opencontainers.image.source="https://github.com/djr747/external-dns-technitium-webhook" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Red Hat" \
      org.opencontainers.image.base.name="registry.access.redhat.com/ubi10/ubi-minimal"

# Install Python 3.12 and shadow-utils for user management
RUN microdnf update -y && \
    microdnf install -y python3.12 shadow-utils && \
    microdnf clean all && \
    rm -rf /var/cache/yum

# Create non-root user
RUN useradd -r -u 1000 -m -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    LISTEN_ADDRESS="0.0.0.0" \
    LISTEN_PORT="8888"

# Copy application code
WORKDIR /app
COPY --chown=appuser:appuser external_dns_technitium_webhook ./external_dns_technitium_webhook

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8888/healthz', timeout=3)" || exit 1

# Expose port
EXPOSE 8888

# Run the application
CMD ["python", "-m", "uvicorn", "external_dns_technitium_webhook.main:app", "--host", "0.0.0.0", "--port", "8888", "--no-access-log"]
