# Copilot Instructions: ExternalDNS Technitium Webhook

## Project Overview
This is a high-performance **ExternalDNS webhook provider** for Technitium DNS Server, built with FastAPI. It runs as a **sidecar container** alongside ExternalDNS in Kubernetes to automatically sync DNS records from Kubernetes resources (Ingress, Service) to Technitium DNS.

## Architecture & Component Flow
```
K8s Resources → ExternalDNS → Webhook (FastAPI) → Technitium DNS Server
```

Key components in `external_dns_technitium_webhook/`:
- **`main.py`** - FastAPI app with lifecycle management, signal handling, and async context
- **`handlers.py`** - ExternalDNS webhook endpoints (`/health`, `/`, `/records`, `/adjustendpoints`)
- **`technitium_client.py`** - Async HTTP client with auto-authentication and zone management
- **`models.py`** - Pydantic models for ExternalDNS protocol and DNS record types
- **`config.py`** - Environment-based configuration with Pydantic Settings
- **`app_state.py`** - Application state management with async initialization
- **`middleware.py`** - Rate limiting and request size validation middleware

## Development Workflow
```bash
# Setup (Python 3.13)
make install-dev          # Install with dev dependencies

# Development cycle
make format               # Ruff formatter (black-style)
make lint                 # Ruff linter (replaces flake8, isort)
make type-check           # mypy with strict settings
make test                 # pytest with async support
make test-cov             # Coverage with HTML reports (CI gates at 95%)
make security             

make all                 # Run full CI pipeline locally

# Docker workflow
make docker-build        # Build Docker image
make docker-run          # Run container with example config
make docker-compose-up   # Start with docker-compose
make docker-compose-logs # View logs
make docker-compose-down # Stop services
```

**Important:** Always use `make` commands, not direct tool invocation. The project uses:
- **ruff** for linting and formatting
- **mypy** for type checking with strict configuration
- **pyright** for additional type checking (Pylance-compatible)
- All three tools must pass for code to be merged. CI test coverage is required to be >= 95%.

## Core Patterns & Conventions

### 1. Async-First Architecture
All I/O operations use async/await:
```python
async def handler(state: AppState) -> ExternalDNSResponse:
    await state.ensure_ready()  # Async initialization
    records = await state.client.get_records(zone)
    return ExternalDNSResponse(content=records)
```

### 2. Dependency Injection via FastAPI State
Application state is injected through FastAPI dependency system:
```python
def get_app_state(app: FastAPI) -> AppState:
    return app.state.app_state
```

async def my_handler(state: AppState = Depends(get_app_state)):
    # Handler logic here
```

### 3. ExternalDNS Protocol Compliance
Use custom JSON response with specific media type:
```python
class ExternalDNSResponse(JSONResponse):
    media_type = "application/external.dns.webhook+json;version=1"
```

### 4. Error Handling & Security
- Sanitize error messages to prevent information disclosure (see `sanitize_error_message()`)
- Use structured exceptions with context (`TechnitiumError`, `InvalidTokenError`)
- Log at appropriate levels (DEBUG for API calls, WARNING for retries, ERROR for failures)

### 5. Pydantic Model Patterns
Models use `alias` for ExternalDNS camelCase and validation:
```python
class Endpoint(BaseModel):
    dns_name: str = Field(..., alias="dnsName")
    record_ttl: Optional[int] = Field(None, alias="recordTTL", ge=0, le=2147483647)
    model_config = {"populate_by_name": True}  # Accept both snake_case and camelCase
```

## Key Integration Points

### Environment Configuration
Required vars (see `config.py`):
- `TECHNITIUM_URL` - DNS server endpoint
- `TECHNITIUM_USERNAME/PASSWORD` - Auth credentials (user must be member of **DNS admin** group)
- `ZONE` - Primary DNS zone
- `DOMAIN_FILTERS` - Semicolon-separated domain list

**Important:** The Technitium user account must be added to the **DNS admin group** in Technitium's Administration panel to access the API. Zone-level permissions alone are insufficient.

### Technitium API Integration
- **Auto-authentication**: Client handles token renewal transparently
- **Zone auto-creation**: Missing zones are created automatically
- **10 DNS record types**: A, AAAA, CNAME, TXT, ANAME, CAA, URI, SSHFP, SVCB, HTTPS
- **Advanced options**: Comments, expiry TTL, PTR records via provider-specific properties

### Testing Patterns
- Use `pytest-asyncio` for async tests
- `conftest.py` resets environment variables between tests
- Mock external HTTP calls with `pytest-mock`
- Test both success and error scenarios for all handlers

### Type Checking Standards
The project uses **three** type checkers to ensure type safety:
1. **ruff** - Fast linting with type-aware rules (F401, F841, etc.)
2. **mypy** - Strict type checking with `--strict` mode
3. **pyright** - VS Code/Pylance compatible type checking (basic mode)

**Before committing code:**
- Run `make lint` to verify ruff + pyright pass
- Run `make type-check` to verify mypy + pyright pass
- Fix all errors (zero tolerance for type errors in source code)
- Warnings in tests are acceptable if they don't affect functionality

**Common type issues to avoid:**
- Missing type hints on function parameters and return types
- Using `Any` when a more specific type is available
- Unused imports (caught by both ruff and pyright)
- Missing return type annotations on async functions
- Untyped decorators (use `# type: ignore[misc]` for FastAPI routes if needed)

**Pyright-specific notes:**
- Configured in `pyproject.toml` under `[tool.pyright]`
- Uses "basic" type checking mode (less strict than mypy)
- Reports unused imports, variables, and functions
- Test files have relaxed settings for test fixtures
- FastAPI route handlers ignore "unused function" warnings

## Deployment Context
- **Sidecar deployment**: Runs alongside ExternalDNS in same pod
- **Health checks**: `/healthz` endpoint for Kubernetes probes
- **Container image**: Multi-stage build using Chainguard Python latest base images (minimal, non-root, curated by Chainguard)
- **Middleware**: Rate limiting (1000 req/min, 10 burst) and request size limits (1MB default)

Note: We require the security workflow (`.github/workflows/security.yml`) to run on every pull request and on a schedule. Protect the `main` branch with branch protection rules that require the security workflow to pass before merging.

## Common Tasks

### Adding New DNS Record Type
1. Add data model in `models.py` following existing patterns
2. Update `technitium_client.py` to handle the new type in `add_record()`
3. Add validation logic in `handlers.py` if needed
4. Write tests covering creation, validation, and error cases

### Extending Technitium Client
- Follow async patterns with proper error handling
- Use `TechnitiumError` for API errors with context
- Add request logging at DEBUG level
- Handle authentication renewal transparently

### Configuration Changes
- Add new settings to `Config` class in `config.py`
- Use Pydantic validators for complex validation
- Document in README and environment examples
- Ensure proper handling in Docker/K8s deployment examples

When working on this codebase, prioritize async/await patterns, comprehensive error handling, and ExternalDNS protocol compliance. The webhook must be reliable in production Kubernetes environments.

## API Endpoints Reference
The webhook implements the ExternalDNS webhook specification:
- **`GET /health`** - Health check (200 OK when ready, 503 otherwise)
- **`GET /`** - Negotiate domain filters (returns `filters` and `exclude` arrays)
- **`GET /records`** - Retrieve current DNS records from Technitium
- **`POST /adjustendpoints`** - Adjust endpoints before processing (validate/transform)
- **`POST /records`** - Apply DNS record changes (create/delete operations)

All responses use custom media type: `application/external.dns.webhook+json;version=1`

## Troubleshooting & Debugging
- Set `LOG_LEVEL=DEBUG` in environment for detailed API call traces
- Health endpoint `/health` returns 503 if not ready (check logs for initialization errors)
- Validate required env vars: `TECHNITIUM_URL`, `TECHNITIUM_USERNAME`, `TECHNITIUM_PASSWORD`, `ZONE`
- Use `make test` to verify code changes before deployment
- Check Technitium API connectivity with curl: 
  - HTTP: `curl -X POST http://<server>:5380/api/user/login`
  - HTTPS: `curl -X POST https://<server>:53443/api/user/login` (use `-k` for self-signed certs)
- Technitium DNS uses port 5380 for HTTP and port 53443 for HTTPS
- For self-signed certificates, set `TECHNITIUM_VERIFY_SSL=false`
- Rate limiting: default 1000 req/min with burst of 10; override via `REQUESTS_PER_MINUTE` and `RATE_LIMIT_BURST`
- Request size limit: 1MB default (adjust via `RequestSizeLimitMiddleware`)

## Security Best Practices
- **Never log passwords**: Config class redacts password in `__repr__()` and `model_dump()`
- **Sanitize errors**: Use `sanitize_error_message()` to strip sensitive patterns before client response
- **Token renewal**: Client handles auth token refresh transparently on 401 errors
- **Middleware protection**: Rate limiting and request size validation prevent abuse
- **Container security**: Runs as non-root user (UID 1000), read-only filesystem recommended

## Code Quality Standards
- **Type safety**: Strict mypy configuration enforced (`disallow_untyped_defs`, `check_untyped_defs`)
- **Linting**: Ruff with pycodestyle, pyflakes, isort, flake8-bugbear, pyupgrade rules
- **Test coverage**: pytest with asyncio support, mock external HTTP calls with pytest-mock
- **Security scanning**: semgrep for code analysis
- **Formatting**: Ruff format (black-compatible, 100 char line length)
- **Python version**: 3.11+ required (uses modern type hints like `dict[str, Any]`)

## Provider-Specific Properties
Advanced Technitium features via `providerSpecific` in Endpoint model:
```python
# Example: Record with comment and expiry
{
  "dnsName": "test.example.com",
  "recordType": "A",
  "targets": ["192.0.2.1"],
  "providerSpecific": [
    {"name": "comment", "value": "Auto-generated by ExternalDNS"},
    {"name": "expiryTtl", "value": "86400"},  # Auto-delete after 24h
    {"name": "createPtrZone", "value": "true"}  # Auto-create PTR record
  ]
}
```

Supported properties: `comment`, `expiryTtl`, `disabled`, `createPtrZone` (see handlers.py)

## Implementation Guidelines

### Code Quality & Testing
- **Test coverage**: Ensure all new code has corresponding tests (CI enforces >= 95% coverage)
- **PEP 8 compliance**: Follow Python style guide and project-specific ruff rules
- **Type hints**: Use strict typing for all functions (mypy enforces this)
- **Async patterns**: All I/O operations must use async/await consistently
- **Mock external calls**: Use `pytest-mock` to mock Technitium API in tests
- **Test isolation**: Ensure tests do not depend on each other (use fixtures)
- **Performance testing**: Include performance tests to identify bottlenecks
- **Type checking**: Ensure ruff, mypy, and pyright pass without errors before merging and do not introduce new type errors or warnings. Ignoring type errors is not allowed in source code.

### Documentation & Maintenance
- **Update docs**: Document new features in README.md and relevant docs/ files
- **CHANGELOG.md**: Add entries for each release following semantic versioning
- **Inline comments**: Document complex logic, especially DNS record transformations
- **API compatibility**: Maintain backward compatibility with ExternalDNS protocol

### Release Process (Version-Driven Automation)
The project uses **version-driven releases** controlled entirely through `pyproject.toml`:

**Release Workflow:**
1. **Before PR**: Update `version = "X.Y.Z"` in `pyproject.toml` (follow semantic versioning)
2. **Update CHANGELOG.md**: Add entry under new version with all changes
3. **PR & Merge**: Create PR, pass all tests, merge to main
4. **Auto-Tag Workflow** (auto-tag-on-main.yml): Automatically detects `pyproject.toml` change on main:
   - Extracts version from `pyproject.toml`
   - Creates git tag `vX.Y.Z`
   - Creates draft GitHub Release with basic info
5. **Release Workflow** (release.yml): Triggers on release publication:
   - Builds Docker image
   - Publishes to registry
   - Updates release notes with artifacts

**Dependabot Integration:**
When Dependabot creates PRs to update dependencies, merging them will also trigger releases (patch version bump in PR description). This is expected behavior and enables automated security updates.

**Key Points:**
- **Single source of truth**: `pyproject.toml` version field
- **No manual tag creation**: Automation handles it
- **Version bump in PR**: Makes release intent clear during review
- **CHANGELOG first**: Always document changes before release
- **For every release**: Remember to update `pyproject.toml` version AND `CHANGELOG.md`

### Development Workflow
- **GitHub Issues**: Track bugs and features using issue templates
- **Pull requests**: Thoroughly review for code quality, security, and pattern adherence
- **CI/CD**: All tests must pass before merge (format, lint, type-check, test, security)
- **Dependencies**: Regularly update with `pip list --outdated` and check for CVEs
- **Releases**: Update `pyproject.toml` version field to trigger release automation

### Security & Production
- **Credential handling**: Never log passwords or tokens (use Config redaction patterns)
- **Dependency scanning**: Run `make security` before releases
- **Container security**: Follow non-root user pattern, minimal base images
- **Kubernetes best practices**: Resource limits, health probes, graceful shutdown

### Performance & Reliability
- **Graceful shutdown**: Use signal handlers in main.py to cleanup connections
- **Connection pooling**: httpx.AsyncClient reuses connections to Technitium
- **Error recovery**: Implement retry logic for transient failures
- **Resource management**: Use async context managers for proper cleanup

### Monitoring & Observability
- **Structured logging**: Use appropriate log levels (DEBUG/INFO/WARNING/ERROR)
- **Health checks**: `/healthz` endpoint must accurately reflect readiness state
- **Performance**: Monitor response times and optimize for production workloads
- **Future**: Plan for Prometheus metrics and OpenTelemetry tracing integration

## Release Workflow (CRITICAL - Read docs/RELEASE.md)

**ONLY production dependency updates trigger releases.** The workflow is:

### Production Dependencies (fastapi, uvicorn, httpx, pydantic)
1. **Dependabot creates PR on `develop` branch** (NOT main)
2. **Review and merge to develop**
3. **Manually bump version in pyproject.toml** (e.g., 0.2.8 → 0.2.9)
4. **Update CHANGELOG.md** with dependency and version changes
5. **Commit**: `git commit -m "deps: bump fastapi to 0.121.0 + release v0.2.9"`
6. **Create PR**: develop → main
7. **Merge to main** → **Triggers release.yml**
8. **Release pipeline runs automatically:**
   - `check-version-changed` detects `version =` line changed ✅
   - `create-git-tag` creates `vX.Y.Z` git tag
   - `create-release` creates GitHub release
   - `build-and-publish-container` builds multi-arch Docker image
   - Uploads SBOM, security scans, signs container

### Development Dependencies (pytest, ruff, mypy, semgrep, etc.)
1. **Dependabot creates PR on `main` branch** automatically
2. **Merge directly to main** - no version bump needed
3. **Release is skipped** (version-changed detection catches this)
4. **No git tag, no release, no container build**

### Key Points
- **Never manually merge production deps to main** - always go through develop + version bump first
- **Version bump in pyproject.toml is the ONLY trigger** for releases
- **CHANGELOG.md must be updated** with every release
- **Dev-only updates never create releases** - version detection prevents this
- **If PR targets wrong branch**, close it and follow the proper workflow above

**See `docs/RELEASE.md` for complete detailed workflow.**

## Additional Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://pydantic.dev/)
- [Technitium DNS Server API](https://technitium.com/dns/docs/api/)
- [ExternalDNS Webhook Protocol](https://external-dns.readthedocs.io/en/latest/)