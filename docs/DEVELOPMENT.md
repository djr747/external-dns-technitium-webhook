# Development Guide# Development Guide# Development Guide



This document complements the README with deeper contributor guidance. All commands assume a POSIX shell.



## PrerequisitesThis document complements the README with deeper contributor guidance. All commands assume a POSIX shell.## 🚀 Quick Start (3 Steps)

- Python 3.11+

- `pip` and `virtualenv`

- (Optional) Docker + Docker Compose

## Prerequisites```bash

## Environment Setup

```bash- Python 3.11+# 1. Install dependencies

git clone https://github.com/djr747/external-dns-technitium-webhook.git

cd external-dns-technitium-webhook- `pip` and `virtualenv`pip install -e ".[dev]"

python -m venv .venv

source .venv/bin/activate- (Optional) Docker + Docker Compose

make install-dev

```# 2. Set environment variables (or create .env)



Environment variables can be loaded via `.env` or exported directly. At minimum specify:## Environment Setupexport TECHNITIUM_URL="http://localhost:5380"

```bash

export TECHNITIUM_URL="http://localhost:5380"```bashexport TECHNITIUM_USERNAME="admin"

export TECHNITIUM_USERNAME="admin"

export TECHNITIUM_PASSWORD="admin"git clone https://github.com/djr747/external-dns-technitium-webhook.gitexport TECHNITIUM_PASSWORD="admin"

export ZONE="example.com"

```cd external-dns-technitium-webhookexport ZONE="example.com"

Optional variables: `TECHNITIUM_FAILOVER_URLS`, `DOMAIN_FILTERS`, `CATALOG_ZONE`, `REQUESTS_PER_MINUTE`, `RATE_LIMIT_BURST`, `TECHNITIUM_TIMEOUT`, `LOG_LEVEL`, `LISTEN_ADDRESS`, `LISTEN_PORT`.

python -m venv .venv

## Core Commands

| Task | Command |source .venv/bin/activate# 3. Run the application

| --- | --- |

| Format code | `ruff format .`make install-devpython -m external_dns_technitium_webhook.main

| Lint | `make lint`

| Type check | `make type-check```````

| Run tests | `make test`

| Run tests with coverage | `make test-cov`

| Security scan | `make security`

| Build Docker image | `make docker-build`Environment variables can be loaded via `.env` or exported directly. At minimum specify:## 📚 API Documentation

| Run container locally | `make docker-run`

```bash

## Running the Webhook Manually

```bashexport TECHNITIUM_URL="http://localhost:5380"FastAPI automatically generates interactive API documentation:

python -m external_dns_technitium_webhook.main

```export TECHNITIUM_USERNAME="admin"

The FastAPI docs will be available at `http://localhost:3000/docs`. Logs include connection status, catalog enrollment, and rate-limit warnings.

export TECHNITIUM_PASSWORD="admin"- **Swagger UI**: http://localhost:3000/docs

## Testing Tips

- Individual tests can be executed with `pytest tests/test_handlers.py::test_apply_record_create`.export ZONE="example.com"- **ReDoc**: http://localhost:3000/redoc

- Coverage reports are written to `htmlcov/index.html`.

- Async fixtures rely on `pytest-asyncio`; avoid blocking calls inside tests.```- **OpenAPI JSON**: http://localhost:3000/openapi.json



## Docker & ComposeOptional variables: `TECHNITIUM_FAILOVER_URLS`, `DOMAIN_FILTERS`, `CATALOG_ZONE`, `REQUESTS_PER_MINUTE`, `RATE_LIMIT_BURST`, `TECHNITIUM_TIMEOUT`, `LOG_LEVEL`, `LISTEN_ADDRESS`, `LISTEN_PORT`.

Quick smoke test without Kubernetes:

```bash## Common Commands

cp .env.example .env  # edit credentials first

docker-compose up -d## Core Commands

curl http://localhost:3000/health

```| Task | Command |### Development

Stop services with `docker-compose down` and review logs using `docker-compose logs -f`.

| --- | --- |```bash

## Workflow Checklist

1. Open a feature branch.| Format code | `ruff format .` |make install-dev    # Install with dev dependencies

2. Make code changes and update documentation when behavior changes.

3. Run `make lint`, `make type-check`, `make test-cov`.| Lint | `make lint` |make test          # Run tests

4. Commit with a descriptive message and open a pull request referencing any related issues.

| Type check | `make type-check` |make test-cov      # Run tests with coverage (currently at 80%)

## Troubleshooting

- **401 responses from Technitium**: verify username/password and ensure the user has zone write permissions.| Run tests | `make test` |make lint          # Check linting with ruff

- **503 from `/health`**: the webhook failed to initialize; check logs for endpoint connection errors or missing zones.

- **429 responses**: adjust `REQUESTS_PER_MINUTE` / `RATE_LIMIT_BURST` or slow the client.| Run tests with coverage | `make test-cov` |make format        # Format code with ruff

- **Token renewal warnings**: confirm the webhook can reach the Technitium API over the network.

| Security scan | `make security` |make type-check    # Run mypy type checking

| Build Docker image | `make docker-build` |make security      # Run bandit + safety scans

| Run container locally | `make docker-run` |make all           # Run full CI pipeline locally

```

## Running the Webhook Manually

```bash### Docker

python -m external_dns_technitium_webhook.main```bash

```make docker-build           # Build Docker image

The FastAPI docs will be available at `http://localhost:3000/docs`. Logs include connection status, catalog enrollment, and rate-limit warnings.make docker-run            # Run Docker container

make docker-compose-up     # Start all services

## Testing Tipsmake docker-compose-down   # Stop all services

- Individual tests can be executed with `pytest tests/test_handlers.py::test_apply_record_create`.make docker-compose-logs   # View logs

- Coverage reports are written to `htmlcov/index.html`.```

- Async fixtures rely on `pytest-asyncio`; avoid blocking calls inside tests.

## Project Structure

## Docker & Compose

Quick smoke test without Kubernetes:```

```bashexternal-dns-technitium-webhook/

cp .env.example .env  # edit credentials first├── external_dns_technitium_webhook/

docker-compose up -d│   ├── __init__.py           # Package initialization

curl http://localhost:3000/health│   ├── main.py               # Application entry point

```│   ├── config.py             # Configuration management

Stop services with `docker-compose down` and review logs using `docker-compose logs -f`.│   ├── models.py             # Data models

│   ├── app_state.py          # Application state

## Workflow Checklist│   ├── handlers.py           # API handlers

1. Open a feature branch.│   └── technitium_client.py  # Technitium API client

2. Make code changes and update documentation when behavior changes.├── tests/

3. Run `make lint`, `make type-check`, `make test-cov`.│   ├── __init__.py

4. Commit with a descriptive message and open a pull request referencing any related issues.│   ├── conftest.py           # Test configuration

│   ├── test_config.py

## Troubleshooting│   ├── test_models.py

- **401 responses from Technitium**: verify username/password and ensure the user has zone write permissions.│   ├── test_technitium_client.py

- **503 from `/health`**: the webhook failed to initialize; check logs for endpoint connection errors or missing zones.│   └── test_handlers.py

- **429 responses**: adjust `REQUESTS_PER_MINUTE` / `RATE_LIMIT_BURST` or slow the client.├── .github/

- **Token renewal warnings**: confirm the webhook can reach the Technitium API over the network.│   └── workflows/            # GitHub Actions

│       ├── ci.yml
│       ├── security.yml
│       ├── docker.yml
│       └── release.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
└── LICENSE
```

## Development Workflow

### Initial Setup

```bash
# Clone the repository
```bash
git clone https://github.com/djr747/external-dns-technitium-webhook.git
cd external-dns-technitium-webhook

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
make install-dev
```

### Making Changes

1. **Create a branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Write code
   - Add tests
   - Update documentation

3. **Run checks**
   ```bash
   make format      # Format code
   make lint        # Check linting
   make type-check  # Type checking
   make test        # Run tests
   make security    # Security scans
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "Add my feature"
   git push origin feature/my-feature
   ```

5. **Create Pull Request**

### Running Locally

#### With Python

```bash
# Set environment variables
export TECHNITIUM_URL="http://localhost:5380"
export TECHNITIUM_USERNAME="admin"
export TECHNITIUM_PASSWORD="admin"
export ZONE="example.com"
export LOG_LEVEL="DEBUG"

# Run the application
python -m external_dns_technitium_webhook.main
```

#### With Docker

```bash
# Build image
make docker-build

# Run container
make docker-run
```

#### With Docker Compose

```bash
# Start all services (Technitium + Webhook)
make docker-compose-up

# View logs
make docker-compose-logs

# Stop services
make docker-compose-down
```

### Testing

#### Run All Tests

```bash
make test
```

#### Run with Coverage

```bash
make test-cov
```

#### Run Specific Tests

```bash
pytest tests/test_handlers.py -v
pytest tests/test_handlers.py::test_health_check_ready -v
```

#### Watch Mode (with pytest-watch)

```bash
pip install pytest-watch
ptw
```

### API Testing

#### Test Endpoints Locally

```bash
# Health check
curl http://localhost:3000/health

# Get domain filter
curl http://localhost:3000/

# List DNS records
curl http://localhost:3000/records

# Adjust endpoints (validation)
curl -X POST http://localhost:3000/adjustendpoints \
  -H "Content-Type: application/external.dns.webhook+json;version=1" \
  -d '[{"dnsName":"test.example.com","targets":["1.2.3.4"],"recordType":"A"}]'

# Create A record
curl -X POST http://localhost:3000/records \
  -H "Content-Type: application/external.dns.webhook+json;version=1" \
  -d '{
    "create": [{
      "dnsName": "test.example.com",
      "targets": ["1.2.3.4"],
      "recordType": "A",
      "recordTTL": 3600,
      "setIdentifier": ""
    }]
  }'
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TECHNITIUM_URL` | ✅ | - | Technitium DNS server URL (e.g., `http://localhost:5380`) |
| `TECHNITIUM_USERNAME` | ✅ | - | Technitium admin username |
| `TECHNITIUM_PASSWORD` | ✅ | - | Technitium admin password |
| `ZONE` | ✅ | - | Primary DNS zone to manage (e.g., `example.com`) |
| `LISTEN_ADDRESS` | ❌ | `0.0.0.0` | Server bind address |
| `LISTEN_PORT` | ❌ | `3000` | Server listen port |
| `DOMAIN_FILTERS` | ❌ | - | Semicolon-separated domain filters (e.g., `example.com;test.com`) |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Code Quality

#### Formatting

```bash
# Format code
make format

# Check formatting
make format-check
```

#### Linting

```bash
# Run Ruff
make lint

# Auto-fix issues
ruff check --fix .
```

#### Type Checking

```bash
make type-check
```

#### Security Scanning

```bash
# Run all security scans
make security

# Individual scans
bandit -r external_dns_technitium_webhook

```

### Building Docker Image

```bash
# Build for current platform
docker build -t external-dns-technitium-webhook:latest .

# Build for multiple platforms
docker buildx build --platform linux/amd64,linux/arm64 \
  -t external-dns-technitium-webhook:latest .
```

### Debugging

#### Enable Debug Logging

```bash
export LOG_LEVEL="DEBUG"
python -m external_dns_technitium_webhook.main
```

#### Debug in VS Code

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Main",
      "type": "python",
      "request": "launch",
      "module": "external_dns_technitium_webhook.main",
      "env": {
        "TECHNITIUM_URL": "http://localhost:5380",
        "TECHNITIUM_USERNAME": "admin",
        "TECHNITIUM_PASSWORD": "admin",
        "ZONE": "example.com",
        "LOG_LEVEL": "DEBUG"
      },
      "console": "integratedTerminal"
    }
  ]
}
```

### API Testing

#### Health Check

```bash
curl http://localhost:3000/health
```

#### Get Domain Filter

```bash
curl http://localhost:3000/
```

#### Get Records

```bash
curl http://localhost:3000/records
```

#### Apply Changes

```bash
curl -X POST http://localhost:3000/records \
  -H "Content-Type: application/json" \
  -d '{
    "create": [
      {
        "dnsName": "test.example.com",
        "targets": ["1.2.3.4"],
        "recordType": "A",
        "recordTTL": 3600
      }
    ]
  }'
```

## CI/CD Pipeline

### Workflows

1. **CI** (`.github/workflows/ci.yml`)
   - Linting and formatting checks
   - Type checking
   - Unit tests with coverage
   - Security scans
   - Docker build test

2. **Security** (`.github/workflows/security.yml`)
   - Trivy container scanning
   - Dependency scanning
   - Code scanning with Bandit
   - CodeQL analysis

3. **Docker** (`.github/workflows/docker.yml`)
   - Multi-platform builds
   - Push to GitHub Container Registry
   - Vulnerability scanning

4. **Release** (`.github/workflows/release.yml`)
   - Create GitHub release
   - Build and publish to PyPI
   - Generate changelog

### Running Workflows Locally

Use [act](https://github.com/nektos/act) to run workflows locally:

```bash
# Install act
brew install act  # macOS
# or download from releases

# Run CI workflow
act -W .github/workflows/ci.yml
```

## Troubleshooting

### Import Errors

```bash
# Reinstall in development mode
pip install -e ".[dev]"
```

### Test Failures

```bash
# Run with verbose output
pytest -vv

# Run with print statements
pytest -s
```

### Docker Build Issues

```bash
# Clear build cache
docker builder prune

# Rebuild without cache
docker build --no-cache -t external-dns-technitium-webhook:latest .
```

### Type Checking Errors

```bash
# Install type stubs
pip install types-urllib3

# Run mypy with verbose output
mypy --show-error-codes external_dns_technitium_webhook
```

## Best Practices

1. **Always run tests before committing**
2. **Keep dependencies up to date**
3. **Write tests for new features**
4. **Document public APIs**
5. **Use type hints**
6. **Follow PEP 8 style guide**
7. **Keep functions small and focused**
8. **Handle errors gracefully**
9. **Log important events**
10. **Review security scan results**

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Technitium DNS API](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md)
- [ExternalDNS Documentation](https://kubernetes-sigs.github.io/external-dns/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
