# ExternalDNS Technitium Webhook

[![CI](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/ci.yml/badge.svg)](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/ci.yml)
[![Security](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/security.yml/badge.svg)](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/djr747/external-dns-technitium-webhook/branch/main/graph/badge.svg)](https://codecov.io/gh/djr747/external-dns-technitium-webhook)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

FastAPI webhook provider that lets [ExternalDNS](https://github.com/kubernetes-sigs/external-dns) manage records on a [Technitium DNS Server](https://technitium.com/dns/). Deploy it as a sidecar next to ExternalDNS to translate webhook events into Technitium API calls.

## Highlights
- Async-first architecture with graceful startup/shutdown and token auto-renewal
- Technitium client with failover rotation, zone auto-create, and catalog enrollment
- Rate limiting and request size middleware for defensive operation (enabled by default: REQUESTS_PER_MINUTE=1000, RATE_LIMIT_BURST=10)
- Optional request compression (gzip) for large payloads sent to remote Technitium servers
- 10 DNS record types supported; provider-specific properties are preserved end-to-end

## How It Fits Together
```
Kubernetes resources → ExternalDNS → Webhook (FastAPI) → Technitium DNS API
```
The webhook maintains shared application state (HTTP client, auth token, readiness flag) and exposes the ExternalDNS webhook contract: `/health`, `/`, `/records`, `/adjustendpoints`, and `/records`.

## DevelopmentQuick Start
```bash
git clone https://github.com/djr747/external-dns-technitium-webhook.git
cd external-dns-technitium-webhook
python -m venv .venv
source .venv/bin/activate
make install-dev

# minimum configuration
# Use port 5380 for HTTP or 53443 for HTTPS
export TECHNITIUM_URL="http://dns.example.com:5380"  # or https://dns.example.com:53443
export TECHNITIUM_USERNAME="external-dns-webhook"
export TECHNITIUM_PASSWORD="changeme"
export ZONE="example.com"
# For self-signed certificates with HTTPS, disable SSL verification
# export TECHNITIUM_VERIFY_SSL="false"

python -m external_dns_technitium_webhook.main
```
Interactive API docs live at `http://127.0.0.1:3000/docs` while the server runs.

## Configuration
Environment variables map directly to `external_dns_technitium_webhook.config.Config`:

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `TECHNITIUM_URL` | ✅ | — | Primary Technitium API endpoint (port 5380 for HTTP, 53443 for HTTPS) |
| `TECHNITIUM_USERNAME` | ✅ | — | Service account for the webhook |
| `TECHNITIUM_PASSWORD` | ✅ | — | Password for the service account |
| `ZONE` | ✅ | — | Forward zone managed through ExternalDNS |
| `DOMAIN_FILTERS` | ❌ | — | Semicolon-separated allowlist for ExternalDNS |
| `TECHNITIUM_FAILOVER_URLS` | ❌ | — | Semicolon-separated fallback endpoints |
| `CATALOG_ZONE` | ❌ | — | Catalog zone joined when the endpoint is writable |
| `TECHNITIUM_VERIFY_SSL` | ❌ | `true` | Verify TLS certificates; set to `false` for self-signed certs |
| `TECHNITIUM_CA_BUNDLE_FILE` | ❌ | — | Path to PEM file with CA cert(s) for private CAs; mounted via ConfigMap |
| `LISTEN_ADDRESS` | ❌ | `0.0.0.0` | Bind address for the FastAPI server |
| `LOG_LEVEL` | ❌ | `INFO` | Python logging level |
| `TECHNITIUM_TIMEOUT` | ❌ | `10.0` | HTTP timeout (seconds) for Technitium calls |
| `REQUESTS_PER_MINUTE` | ❌ | `1000` | Token bucket rate limit per client |
| `RATE_LIMIT_BURST` | ❌ | `10` | Burst capacity for the rate limiter |

## Security & Container Image

This project uses **Chainguard Python** base images for maximum security:
- 🔒 **Zero CVEs** - Ultra-minimal images with no unnecessary packages
- 🔄 **Daily Updates** - Automated security patches within 24 hours
- 📋 **SLSA Level 3** - Supply chain security with signed provenance
- 🚫 **Non-root** - Runs as UID 65532 (`nonroot`) by default
- 📦 **Minimal** - ~40MB final image (vs 100MB+ for typical Python containers)

For security disclosures, see [docs/SECURITY.md](docs/SECURITY.md).

## Development Workflow
Run the project's quality gates before opening a pull request:
```bash
make lint        # Ruff lint + format check
make type-check  # mypy (strict) + Pyright
make test-cov    # pytest with coverage
make test-integration  # Integration tests with local kind cluster
```
See `docs/DEVELOPMENT.md` for contributor tips and `docs/LOCAL_TESTING.md` for local integration testing.

## Documentation Map
- [API reference](docs/API.md) – Webhook endpoints and payload examples
- [Credentials setup](docs/CREDENTIALS_SETUP.md) – Create Technitium credentials and Kubernetes secrets
- [Kubernetes deployment (Helm)](docs/deployment/kubernetes.md) – Helm-based sidecar deployment
- [Development guide](docs/DEVELOPMENT.md) – Extended development guidance and coding conventions
- [Local testing guide](docs/LOCAL_TESTING.md) – Running integration tests locally with kind
- [Performance & reliability](docs/PERFORMANCE.md) – Optimization techniques and tuning guide
- [CI/CD & security](docs/CICD_SECURITY.md) – Overview of GitHub Actions CI/CD and security tooling
- [Architecture](docs/architecture/ARCHITECTURE.md) – System diagram and runtime details
- [Security policy](docs/SECURITY.md) – Security policy and disclosure process

## Contributing & License
Bug reports and pull requests are welcome—see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for expectations. Licensed under the MIT License ([LICENSE](LICENSE)).

> Inspired by [roosmaa/external-dns-technitium-webhook](https://github.com/roosmaa/external-dns-technitium-webhook) and tailored for Technitium-backed ExternalDNS deployments.
