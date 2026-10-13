# Multi-stage build on Docker Hardened Images (DHI) Python 3.14 (Debian 13).
#
# DHI images are built, signed and patched by Docker: the base is rebuilt on
# a schedule from Docker's own Debian packages (versions carry a `+dhiN`
# suffix), so OS security fixes and Python security updates land in new
# pushes of the tag. The tag is therefore floating on the Python 3.14 patch
# line (3.14-debian13 tracks any 3.14.x): every `docker build` pulls the
# newest patched base automatically, with no re-bake/re-pin cycle. (The
# trade-off vs a digest-pinned tag is build-to-build reproducibility; the
# nightly security scan re-checks whatever base the build actually used.)
#
# Pulling requires a DHI registry login (`docker login dhi.io`); CI supplies
# it from the DOCKER_HUB_RO_USER / DOCKER_HUB_RO_PAT repository secrets. The
# free tier is pull-only and self-supported; SLA-backed updates and
# FIPS/STIG variants are part of the paid Hardened Images tier.
FROM dhi.io/python:3.14-debian13 AS builder

# The DHI base defaults to USER 65532 (nonroot). Build as root so the pip
# install writes to the real system /usr/lib/python3/dist-packages; as
# nonroot, pip would otherwise fall back to the user site
# (/home/nonroot/.local/...) and the final image would miss every app dep.
# The final stage runs nonroot, so this root build stage leaves no root in
# the artifact (standard for Debian system-Python images).
USER 0

# DHI runtime images deliberately ship without a shell and without a package
# manager (apt is stripped from the runtime), so every build step below is an
# exec-form invocation and nothing may invoke sh.
WORKDIR /build
COPY pyproject.toml ./
COPY pylock.toml ./

# Install the app's dependencies from the PEP 751 lock file (pylock.toml).
# The lock records every resolved version with its sha256; --require-hashes
# makes pip verify each wheel against those hashes and abort the build if
# any differ, so a build can never silently pull a different (or tampered)
# dependency than the one reviewed and pinned in the lock. This is the
# production (default) group only — the dev/test toolchain stays out of the
# image. The app code itself is copied from source in the final stage and
# run via `python3 -m uvicorn external_dns_technitium_webhook.main:app`, so
# the project package is not installed from the lock (it is excluded via
# `--no-emit-project` at export time).
#
# --target pins the install to the exact directory the final stage copies
# below. The DHI base's CPython reports purelib as
# /usr/lib/python3.14/site-packages, while dist-packages is only reachable
# via the dhi-distpackages.pth shim. A plain `pip install` therefore writes
# the app deps into site-packages, and the dist-packages COPY below captures
# only the base's own pip/setuptools, shipping an image without uvicorn.
# Pinning the target removes that ambiguity.
RUN ["python3", "-m", "pip", "install", "--no-cache-dir", "--only-binary", ":all:", "--require-hashes", "--target", "/usr/lib/python3/dist-packages", "-r", "pylock.toml"]

# Final stage - the same DHI Python 3.14 (Debian 13) image.
FROM dhi.io/python:3.14-debian13 AS final

LABEL org.opencontainers.image.title="ExternalDNS Technitium Webhook" \
      org.opencontainers.image.description="ExternalDNS webhook provider for Technitium DNS Server" \
      org.opencontainers.image.source="https://github.com/djr747/external-dns-technitium-webhook" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Docker Hardened Images" \
      org.opencontainers.image.base.name="dhi.io/python:3.14-debian13"

# Copy the installed packages from the builder. This is a Debian build
# of Python, so system `pip` lands in /usr/lib/python3/dist-packages
# (the Debian default), which /usr/lib/python3.14/site-packages/
# dhi-distpackages.pth already puts on sys.path in both stages. Copying
# site-packages instead would copy an empty directory and ship an image
# without uvicorn. The app entrypoint is `python3 -m uvicorn`, so the
# console scripts in /usr/local/bin are not needed in the final stage.
#
# No --chown: the builder runs as root, so the copied packages stay
# root-owned with the standard 644/755 modes pip sets. The app (UID
# 65532) can read them but not modify them — a compromised app process
# cannot tamper with its own dependencies (self-mutation), and the
# read-only root filesystem set by the Helm chart needs no writable
# paths. The app writes no files at runtime (logs go to stdout,
# PYTHONDONTWRITEBYTECODE=1 suppresses __pycache__).
COPY --from=builder /usr/lib/python3/dist-packages /usr/lib/python3/dist-packages

WORKDIR /app
# Root-owned app source: the app reads it, never writes it, so it is
# immutable to the runtime user (same rationale as the packages above).
COPY external_dns_technitium_webhook ./external_dns_technitium_webhook

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    LISTEN_ADDRESS="0.0.0.0"

# DHI ships the unprivileged nonroot user (UID 65532) and no default user;
# run as nonroot. Uvicorn logs to stdout, so the read-only root filesystem
# (set by the Helm chart) needs no writable paths.
USER 65532

# The image ships no shell and no entrypoint; set python3 explicitly so the
# CMD below runs as a plain python module launch.
ENTRYPOINT ["python3"]

# Health check: Docker does NOT prepend the ENTRYPOINT to an exec-form
# HEALTHCHECK, so the interpreter must be named explicitly here (otherwise it
# would try to exec a binary literally named "-c" and every healthcheck would
# fail). python3, to match the ENTRYPOINT above and the base image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"]

# Expose ports (8888 webhook API, 8080 metrics/health)
EXPOSE 8888 8080

# Using --ws websockets-sansio to avoid deprecated websockets.legacy
# implementation (compatibility with websockets library v14.0+)
CMD ["-m", "uvicorn", "external_dns_technitium_webhook.main:app", "--host", "0.0.0.0", "--port", "8888", "--no-access-log", "--ws", "websockets-sansio"]
