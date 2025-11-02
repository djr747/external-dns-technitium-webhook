# Development Guide

This document provides guidance for contributing to the external-dns-technitium-webhook project.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/djr747/external-dns-technitium-webhook.git
cd external-dns-technitium-webhook

# 2. Install development dependencies
make install-dev

# 3. Run full CI pipeline locally
make all
```

## Prerequisites

- Python 3.11+
- pip and virtualenv
- Git
- (Optional) Docker + Docker Compose
- (Optional) Make

## Environment Setup

### Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# or
.venv\Scripts\activate        # Windows
```

### Install Dependencies

```bash
make install-dev
# or
pip install -e ".[dev]"
```

### Configure Environment

```bash
export TECHNITIUM_URL="http://localhost:5380"
export TECHNITIUM_USERNAME="admin"
export TECHNITIUM_PASSWORD="admin"
export ZONE="example.com"
```

## Development Workflow

### Code Quality Checks

```bash
make lint         # Ruff format + check
make type-check   # mypy + pyright strict
make test         # pytest with coverage
make all          # Run all checks
```

### Testing

```bash
# Full test suite
make test

# Specific test
pytest tests/test_handlers.py::test_health_endpoint -v

# With coverage
pytest --cov=external_dns_technitium_webhook tests/

# HTML report
pytest --cov=external_dns_technitium_webhook --cov-report=html tests/
# Open htmlcov/index.html
```

Coverage requirement: CI gates at >= 95%.

### Running Locally

```bash
# Start webhook server
python -m uvicorn external_dns_technitium_webhook.main:app \
  --host 0.0.0.0 \
  --port 3000 \
  --reload

# Test endpoints
curl http://127.0.0.1:3000/health
curl http://127.0.0.1:3000/
```

### Docker Development

```bash
make docker-build
make docker-compose-up
make docker-compose-logs
make docker-compose-down
```

## Project Structure

```
external-dns-technitium-webhook/
├── external_dns_technitium_webhook/
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Environment configuration
│   ├── app_state.py           # Application state management
│   ├── handlers.py            # ExternalDNS webhook endpoints
│   ├── technitium_client.py   # Async HTTP client for Technitium
│   ├── models.py              # Pydantic request/response models
│   └── middleware.py          # Rate limiting, security middleware
├── tests/
│   ├── conftest.py            # Pytest fixtures
│   ├── test_config.py         # Configuration tests
│   ├── test_handlers.py       # Webhook endpoint tests
│   ├── test_technitium_client.py  # Client tests
│   └── ...
├── docs/                      # Documentation
├── Dockerfile                 # Container image
├── docker-compose.yml         # Development stack
├── Makefile                   # Common tasks
└── README.md                  # Project overview
```

## Key Modules

### `main.py`
- FastAPI app initialization
- Lifespan management (startup/shutdown)
- Signal handlers for graceful shutdown

### `config.py`
- Environment variable parsing
- Validation for paths, URLs, credentials
- Fail-fast on misconfiguration

### `app_state.py`
- Global state management
- Async initialization on startup
- TechnitiumClient instances

### `handlers.py`
- `/health` - Health/readiness probes
- `GET /` - Domain filter negotiation
- `GET /records` - Retrieve DNS records
- `POST /records` - Apply record changes

### `technitium_client.py`
- Async HTTP client using httpx
- Auto-authentication with token refresh
- All 10 DNS record types supported
- TLS certificate verification support

### `models.py`
- Pydantic models for ExternalDNS protocol
- Technitium API responses
- DNS record types

## Coding Conventions

### Type Hints

All functions must have complete type annotations:

```python
async def my_function(param1: str, param2: int | None = None) -> dict[str, Any]:
    """Function description."""
    return {}
```

### Async/Await

All I/O operations use async patterns:

```python
async def get_records(state: AppState, zone: str) -> list[DnsRecord]:
    records = await state.client.get_records(zone)
    return records
```

### Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Diagnostic info")
logger.info("Operation completed")
logger.warning("Unusual condition")
logger.error("Error condition")
```

## Adding Features

### Adding a DNS Record Type

1. Define model in `models.py`
2. Add handling in `technitium_client.py`
3. Add tests in `tests/test_technitium_client.py`
4. Update `docs/API.md`

### Adding Configuration Options

1. Add field to `Config` class in `config.py`
2. Add validation if needed
3. Update documentation
4. Add tests for validation

## Security Practices

- ✅ Never log credentials
- ✅ Sanitize error messages
- ✅ Use type hints
- ✅ Validate input with Pydantic
- ✅ Use async clients
- ✅ No `# nosec` comments

## Debugging

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
make test
```

### VS Code Debugging

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Webhook Server",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["external_dns_technitium_webhook.main:app"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Breakpoints

```python
breakpoint()  # Python 3.7+
```

## Documentation

Update these files when making changes:

- `README.md` - Quick start and overview
- `docs/DEVELOPMENT.md` - This file
- `docs/API.md` - API endpoint documentation
- `docs/ARCHITECTURE.md` - Architecture overview
- `docs/CREDENTIALS_SETUP.md` - Credential management
- `CHANGELOG.md` - Changes for releases

## Contributing Process

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes and test locally: `make all`
3. Commit with clear messages: `git commit -m "feat: description"`
4. Push to fork: `git push origin feature/your-feature`
5. Open pull request with description
6. Address review feedback and ensure CI passes
7. Merge when approved

## Release Process

Releases follow semantic versioning:

```bash
# Create annotated tag
git tag -a v1.2.3 -m "Release version 1.2.3"

# Push tag (triggers release workflow)
git push origin v1.2.3
```

Release workflow will:
- Build multi-platform images
- Sign with Cosign
- Generate SBOM
- Create GitHub Release with changelog

## Troubleshooting Development

### Import Errors

```bash
pip install -e ".[dev]"
```

### Type Check Failures

```bash
python -m mypy external_dns_technitium_webhook --show-traceback
```

### Test Failures

```bash
pytest tests/ -vv  # Verbose output
pytest tests/ -s   # Show print statements
pytest tests/ -x   # Stop at first failure
```

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [httpx Documentation](https://www.python-httpx.org/)
- [pytest Documentation](https://docs.pytest.org/)
- [Technitium DNS API](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md)
- [ExternalDNS Documentation](https://external-dns.readthedocs.io/)

## Getting Help

- 📖 Check documentation in `docs/`
- 🔍 Search existing GitHub issues
- 💬 Ask in pull request comments
- ✅ Run `make all` to validate setup
