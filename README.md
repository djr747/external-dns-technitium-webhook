# ExternalDNS Technitium Webhook

[![CI](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/ci.yml/badge.svg)](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/ci.yml)
[![Docker](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/docker.yml/badge.svg)](https://github.com/djr747/external-dns-technitium-webhook/actions/workflows/docker.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

FastAPI webhook provider that lets [ExternalDNS](https://github.com/kubernetes-sigs/external-dns) manage records on a [Technitium DNS Server](https://technitium.com/dns/). Deploy it as a sidecar next to ExternalDNS to translate webhook events into Technitium API calls.

## Highlights
- Async-first architecture with graceful startup/shutdown and token auto-renewal
- Technitium client with failover rotation, zone auto-create, and catalog enrollment
- Rate limiting and request size middleware for defensive operation
- 10 DNS record types supported; provider-specific properties are preserved end-to-end

## How It Fits Together
```
Kubernetes resources → ExternalDNS → Webhook (FastAPI) → Technitium DNS API
```
The webhook maintains shared application state (HTTP client, auth token, readiness flag) and exposes the ExternalDNS webhook contract: `/health`, `/`, `/records`, `/adjustendpoints`, and `/records`.

## Quick Start
```bash
git clone https://github.com/djr747/external-dns-technitium-webhook.git
cd external-dns-technitium-webhook
python -m venv .venv
source .venv/bin/activate
make install-dev

# minimum configuration
export TECHNITIUM_URL="http://dns.example.com:5380"
export TECHNITIUM_USERNAME="external-dns-webhook"
export TECHNITIUM_PASSWORD="changeme"
export ZONE="example.com"

python -m external_dns_technitium_webhook.main
```
Interactive API docs live at `http://127.0.0.1:3000/docs` while the server runs.

## Configuration
Environment variables map directly to `external_dns_technitium_webhook.config.Config`:

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `TECHNITIUM_URL` | ✅ | — | Primary Technitium API endpoint |
| `TECHNITIUM_USERNAME` | ✅ | — | Service account for the webhook |
| `TECHNITIUM_PASSWORD` | ✅ | — | Password for the service account |
| `ZONE` | ✅ | — | Forward zone managed through ExternalDNS |
| `DOMAIN_FILTERS` | ❌ | — | Semicolon-separated allowlist for ExternalDNS |
| `TECHNITIUM_FAILOVER_URLS` | ❌ | — | Semicolon-separated fallback endpoints |
| `CATALOG_ZONE` | ❌ | — | Catalog zone joined when the endpoint is writable |
| `LISTEN_ADDRESS` | ❌ | `0.0.0.0` | Bind address for the FastAPI server |
| `LISTEN_PORT` | ❌ | `3000` | Bind port for the FastAPI server |
| `LOG_LEVEL` | ❌ | `INFO` | Python logging level |
| `TECHNITIUM_TIMEOUT` | ❌ | `10.0` | HTTP timeout (seconds) for Technitium calls |
| `REQUESTS_PER_MINUTE` | ❌ | `1000` | Token bucket rate limit per client |
| `RATE_LIMIT_BURST` | ❌ | `10` | Burst capacity for the rate limiter |

## Development Workflow
Run the project’s quality gates before opening a pull request:
```bash
make lint        # Ruff lint + format check
make type-check  # mypy (strict) + Pyright
make test-cov    # pytest with coverage
```
See `docs/DEVELOPMENT.md` for contributor tips and Docker usage.

## Documentation Map
- `docs/API.md` – Webhook endpoints and payload examples
- `docs/CREDENTIALS_SETUP.md` – Create Technitium credentials and Kubernetes secrets
- `docs/deployment/kubernetes.md` – Helm-based sidecar deployment
- `docs/DEVELOPMENT.md` – Extended development guidance
- `docs/CICD_SECURITY.md` – Overview of GitHub Actions CI/CD and security tooling
- `docs/architecture/ARCHITECTURE.md` – System diagram and runtime details
- `docs/SECURITY.md` – Security policy and disclosure process

## Contributing & License
Bug reports and pull requests are welcome—see `docs/CONTRIBUTING.md` for expectations. Licensed under the MIT License (`LICENSE`).

> Inspired by [roosmaa/external-dns-technitium-webhook](https://github.com/roosmaa/external-dns-technitium-webhook) and tailored for Technitium-backed ExternalDNS deployments.
