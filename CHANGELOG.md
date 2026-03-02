# Changelog

All notable changes to this project will be documented in this file.

## [v1.0.3] - 2026-03-01

**Changed:**

- Removed unnecessary `async` keywords from functions that don't perform I/O (SonarCloud findings):
  - `app_state.py`: Converted `ensure_ready()` and `ensure_writable()` to sync methods (only boolean checks)
  - `handlers.py`: Converted `health_check()`, `negotiate_domain_filter()`, and `adjust_endpoints()` to sync (pure data manipulation, response construction)
  - `main.py`: Converted route wrappers `domain_filter` and `adjust` to sync (only call sync handlers)
- Updated all test calls and mocks to reflect the async-to-sync changes:
  - Removed `await` keywords from test calls to now-sync functions
  - Converted test mocks from `AsyncMock()` to `Mock()` for now-sync methods
  - Updated assertion methods from `assert_awaited_once_with()` to `assert_called_once_with()`
- Maintained all I/O-bound operations as genuinely async:
  - `get_records()` and `apply_record()` handlers remain async (call Technitium API)
  - Route wrappers `records` and `apply` remain async (await real I/O)
- Verified no blocking behavior: all sync conversions were for guard functions or pure data manipulation with microsecond execution time
- Test coverage maintained at 100% with 335 tests passing, 0 warnings
- Ruff/pyright: all checks passing with zero errors and warnings

## [v1.0.2] - 2026-03-01

**Fixed & Improved:**

- Addressed the remaining SonarCloud high issues including
  complexity warnings, redundant exception classes and regex cleanup.
- Refactored `technitium_client._post_raw` and `handlers.get_records`
  by extracting helpers (`_parse_response`, `_record_stream`,
  `_extract_targets`) which reduced cognitive complexity.
- Hardened TLS configuration: simplified `TECHNITIUM_VERIFY_SSL`
  override logic and added comprehensive tests; removed nosonar
  comment from SSL check.
- Added `tox.ini` and updated `Makefile` to run tests via `tox` so that
  coverage.xml is generated for SonarCloud.  Ensured coverage remains
  ≥95% and removed remaining `# pragma: no cover` directives.
- Enhanced `run_health_server` to explicitly catch and re‑raise
  `SystemExit`/`KeyboardInterrupt` with proper logging and added tests
  for these conditions.
- Fixed multiple shell scripts (`local-ci-setup/*.sh`,
  `tests/integration/fixtures/init-technitium.sh`) by using `[[`
  conditionals and redirecting error messages to stderr; added missing
  return statements and constants where appropriate.
- Added new unit tests covering parser errors, SSL override, stream
  logic, and health/server behaviors; removed unused test module and
  consolidated coverage.
- Updated documentation and README with warnings regarding insecure
  configuration (`TECHNITIUM_VERIFY_SSL`) and clarified build/test
  workflow.
- Minor lint/type updates across repository; no new ruff/pyright
  warnings remain.

## [v1.0.1] - 2026-03-01

**Changed:**

- Refactored API handlers to reduce cognitive complexity and duplicate logic.
  - Introduced generic `_process_changes` with dedicated `_execute_change` helper.
  - Added constant `API_UNAVAILABLE` and helper functions `_handle_circuit_error` and `_log_fetch_metrics`.
  - Extracted error handling for downstream operations and cleaned up asynchronous logic.
  - Converted several async helpers to synchronous when no await was required.
- Improved `main.py` exception handlers with consistent readiness checks and simplified control flow.
- Hardened TLS handling in `technitium_client.py` and added test for minimum_version fallback.
- Removed stray `tests/test_handlers.py`, consolidated unique test,
  and added new unit tests covering `execute_change` helper and keyboard-interrupt path in `domain_filter`.
- Achieved **100% test coverage** by adding missing test paths and reworking existing suites.
- Addressed SonarCloud findings: complexity reductions, constants for literals, comments, `# pragma: no sonar` where appropriate.
- Updated imports, linting, and formatting across codebase; fixed all ruff/pyright warnings.
- Cleaned up test warnings and pyright issues with `type: ignore` annotations as needed.
- Removed outdated sonar analysis toggles and ensured automatic analysis remains enabled.

## [v1.0.0] - 2026-02-28

**Added:**

- **Circuit Breaker** (`resilience.py`): three-state (CLOSED → OPEN → HALF_OPEN) circuit breaker
  protects all Technitium API calls from cascading failures.
  - `CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default `5`) — consecutive failures before the circuit opens.
  - `CIRCUIT_BREAKER_TIMEOUT` (default `60` s) — seconds the circuit stays open before allowing a
    single probe request.
  - Fast rejection (microseconds instead of the full HTTP timeout) when Technitium is unreachable.
  - `circuit_open` Prometheus error counter incremented on each fast rejection.
  - Health check (`GET /`) returns `503` with `{"circuit_breaker": "open"}` while the circuit is open,
    so Kubernetes probes immediately reflect connectivity failures.

- **DNS record cache**: 30-second in-memory cache for `GET /records` to reduce Technitium API load
  with invalidation on write/delete operations and accompanying unit tests.

- **Metrics endpoint**: Prometheus metrics endpoint added at `/metrics` (served on port 8080).

**Fixed:**

- `handlers.py`: corrected Python-2-style `except AddressValueError, ValueError:` to
  `except ValueError:` (`AddressValueError` is a `ValueError` subclass).
- `main.py`: removed a redundant `except KeyboardInterrupt, SystemExit: raise` clause
  (`KeyboardInterrupt` and `SystemExit` are `BaseException` subclasses that `except Exception` never
  catches anyway).
- `technitium_client.py`: eliminated a redundant double-encode of the request body when gzip
  compression is enabled.

- `handlers.py`: invalidate `get_records` cache when a delete is attempted to ensure cache
  consistency after mutations.

**Changed:**

- Cache TTL and invalidation behavior: expose configurable TTL and document cache invalidation
  options (`CACHE_TTL_SECONDS`, notes in docs and help text).
- CI: bumped several GitHub Action versions (`actions/checkout`, `actions/upload-artifact`,
  `actions/download-artifact`) and other workflow maintenance updates.

**Chore / Tests:**

- Formatting and lint fixes (ruff/black) applied to handlers and tests; syntax fixes and test
  hygiene improvements to address warnings and SonarQube findings.

## [v0.4.3] - 2026-02-28

**Changed:**

- Updated documentation across the repository for clarity and accuracy.
- Adjusted CI/CD workflows (`ci.yml`, `release.yml`, `security.yml`) with recent improvements.
- Hardened Helm example values with security defaults (`automountServiceAccountToken=false`, ephemeral-storage limit) and aligned integration test values; clarified catalog env var name.
- Minor code updates in `main.py`, `health.py`, and `technitium_client.py`.
- Bumped package version and `__version__` constants.

**Removed:**

- Deleted outdated issue templates under `issues/` directory.

## [v0.4.2] - 2026-02-27

**Dependencies:**

- **Updated Production Dependencies:**
  - FastAPI: 0.128.0 → 0.131.0 (performance improvements with Pydantic JSON serialization in Rust, deprecated ORJSONResponse and UJSONResponse)
  - Uvicorn[standard]: 0.40.0 → 0.41.0 (improved lifespan shutdown handling, reduced log level for request limit exceeded messages)
  - Pydantic-settings: 2.12.0 → 2.13.1 (bug fixes for bool field regressions, CLI parsing, nested env vars, self-referential models)

- **Updated Development Dependencies:**
  - Kubernetes: 34.1.0 → 35.0.0 (Kubernetes API v1.35.0 support)
  - Ruff: 0.14.14 → 0.15.2 (expanded default rule set, improved linting capabilities)
  - Pyright: 1.1.407 → 1.1.408 (latest version)

## [v0.4.1] - 2025-12-23

**Fixed:**

- **CodeQL Alert Fix:** Refactored token task cleanup to use `asyncio.gather(return_exceptions=True)` instead of `contextlib.suppress()` for better async pattern compliance and clearer static analysis
- Removed unused `contextlib.suppress` import from app_state.py
- **GitHub Advanced Security Warning:** Added explicit `category` to scheduled rebuild Trivy SARIF upload to prevent stale configuration warnings in code scanning

## [v0.4.0] - 2025-12-23

See [release notes](https://github.com/djr747/external-dns-technitium-webhook/releases/tag/v0.4.0) for details.

## [v0.3.1] - 2025-11-17

**Security:**

- **CodeQL Fixes:** Resolved all GitHub CodeQL security advisories for improved code quality
  - Fixed empty except blocks by using `contextlib.suppress()` instead of bare `pass` (py/empty-except)
  - Restructured exception handling to avoid catching `BaseException` unnecessarily
  - Separated system signal handling (KeyboardInterrupt, SystemExit) with immediate re-raise
  - Consolidated duplicate import styles to use single import pattern (py/import-and-import-from)
  
**Code Quality:**

- Improved code clarity in exception handling paths
- Better adherence
- to Python best practices for exception handling
- Reduced CodeQL security findings from 11 open to 1 (container-level CVE only)

**Dependencies:**

- All production dependencies remain unchanged
- Container base image: Chainguard Python latest (patched daily, zero CVEs)

## [0.3.0] - 2025-11-09

**Changed:**

- **CI/CD Pipeline:** Major overhaul of GitHub Actions workflow for improved reliability and efficiency
  - Streamlined multi-architecture Docker builds with artifact-based job separation
  - Added Chainguard Python version guard to prevent drift between test matrix and base image
  - Implemented atomic manifest push after successful testing
  - Enhanced branch tagging and artifact handling for better CI performance
  - Fixed local tag lookup and verification steps
  - Added comprehensive error handling and cleanup in CI jobs

**Added:**

- **Type Safety:** Improved type annotations with proper `Callable` import from `collections.abc` for URL sanitization helpers
- **Test Coverage:** Added comprehensive unit tests for `run_servers()` function covering:
  - Successful server startup paths
  - Health server timeout scenarios
  - Main server exception handling
  - Signal handler registration
  - Timeout and error logging
- **Test Coverage:** Added test for `ensure_ready()` RuntimeError case in app state tests
- **Coverage Enforcement:** Added `fail_under = 95` to coverage configuration to prevent regression below 95% threshold

**Fixed:**

- **Tests:** Fixed test warnings from unhandled thread exceptions by properly mocking server startup in main function tests
- **Code Quality:** Removed pragma-no-cover shortcuts in favor of proper test coverage for all code paths

## [0.2.9] - 2025-11-03

**Dependencies:**

- Bump fastapi from 0.120.4 to 0.121.0 - adds support for dependencies with scopes and scope="request" for early-exit dependencies

**Documentation:**

- Add comprehensive release workflow documentation in `docs/RELEASE.md`
- Update `copilot-instructions.md` with detailed release workflow section
- Document production vs development dependency separation and automated release triggering

## [0.2.8] - 2025-11-03

**Fixed:**

- **Release Notes:** Corrected base image references in release notes and OCI labels from incorrect "Red Hat UBI10" to actual "Chainguard Python"

## [0.2.7] - 2025-11-03

**Fixed:**

- **Release Automation:** Fixed SBOM and security scan upload in release workflow - added `contents:write` permission to container build job and switched from `softprops/action-gh-release` to `gh release upload` CLI for more reliable asset uploads

## [0.2.6] - 2025-11-02

**Changed:**

- **Release Automation:** Consolidated all release logic into single `release.yml` workflow - removed `auto-tag-on-main.yml`. Workflow now triggers on `pyproject.toml` changes to main, creates git tag, creates GitHub release, then builds/publishes container.

## [0.2.5] - 2025-11-02

**Fixed:**

- **Release Automation:** Simplified release workflow to use GitHub's standard tagging pattern - auto-tag creates tags only, GitHub automatically creates releases from tags, release.yml triggers on release published event (reliable webhook pattern)

## [0.2.4] - 2025-11-02

**Fixed:**

- **Release Workflow Trigger:** Changed trigger from `release: [published]` to `release: [created, published]` to properly handle releases created via GitHub API (API-created releases emit `created` event, not `published`)

## [0.2.3] - 2025-11-02

**Fixed:**

- **Auto-Tag Workflow:** Added git user configuration for tag creation in GitHub Actions runner

## [0.2.2] - 2025-11-02

**Fixed:**

- **Auto-Tag Workflow:** Replaced deprecated `actions/create-release@v1` with `actions/github-script@v7` for proper git tag and GitHub Release creation
- **Workflow Trigger:** Added `workflow_dispatch` trigger to allow manual testing of release automation

## [0.2.1] - 2025-11-02

**Added:**

- **Version-Driven Release Automation:** Implemented `pyproject.toml` as single source of truth for version control
- **Auto-Tag Workflow:** New `auto-tag-on-main.yml` that automatically creates git tags and GitHub releases when version bumps on main
- **CHANGELOG Validation:** Release workflow validates CHANGELOG.md has been updated before creating release (prevents undocumented releases)
- **Dependabot Integration:** Automatic patch releases when Dependabot merges dependency updates with version bumps

**Changed:**

- **Release Process:** Simplified from complex tag-based triggers to clean version-driven automation
- **Release Documentation:** Updated CONTRIBUTING.md and copilot-instructions.md with complete release workflow

## [0.2.0] - 2025-11-02

**Added:**

- **Private Certificate Authority Support:** HTTPS connectivity with private/self-signed certificates via `TECHNITIUM_VERIFY_SSL=false` and `TECHNITIUM_CA_BUNDLE_FILE` environment variables
- **Documentation Excellence:** Comprehensive documentation audit and accuracy verification across 6 core docs (ARCHITECTURE.md, API.md, PERFORMANCE.md, MONITORING.md, DEVELOPMENT.md, CICD_SECURITY.md)
- **Mermaid Diagrams:** Converted 8 ASCII architecture diagrams to modern Mermaid format with enhanced clarity
- **Health Check Architecture:** Documented dual-port architecture (8888 for main API, 8080 for health checks on separate thread)
- **Rate Limiting Documentation:** Detailed 1000 req/min default rate limiting with token bucket algorithm and configurable burst
- **Kubernetes Deployment Guide:** Complete kubectl and Helm deployment examples with security best practices
- **Security Documentation:** Comprehensive security review, credential setup guide, and production checklist with private CA configuration
- **Helm Values Example:** Production-ready `helm/values-webhook-example.yaml` for ExternalDNS integration with private CA support
- **Structured Logging:** External-DNS compatible format applied to ALL logs including uvicorn (HTTP server), httpx (HTTP client), and application loggers (format: time="..." level=... module=... msg="...")
- **Test Infrastructure:** 176 comprehensive tests with 99% code coverage (933/941 lines)
- **CI/CD Pipeline Security:** 5 active security tools (Ruff, mypy, CodeQL, Trivy, Semgrep) with SARIF upload to GitHub Security tab
- **Nightly Chainguard Workflow:** Daily Python version check with automatic PR generation for base image updates
- **Build Provenance:** SLSA Level 3 reproducible builds with SBOM and attestation generation

**Changed:**

- **Port Configuration:** Clarified main API runs on port 8888, health checks on port 8080 (separate thread)
- **Chainguard Python:** Updated to Chainguard Python latest (3.13) with zero-CVE base image
- **CI/CD Tools:** Migrated from Bandit to Semgrep for pattern-based security scanning
- **Logging Format:** Structured logs unified across all sources (app, uvicorn, httpx) using External-DNS format with ISO 8601 timestamps and key-value pairs
- **Makefile:** Added `security` target to `make all` for comprehensive CI pipeline validation
- **Python Version:** datetime.utc → UTC import for Python 3.13+ compatibility
- **Docker Ports:** Updated `make docker-run` from port 3000 to 8888/8080
- **Dependabot Configuration:** Updated from Bandit to Semgrep for security scans

**Fixed:**

- **Logging Implementation:** Applied StructuredFormatter to uvicorn, httpx, and application loggers for consistent External-DNS format across all sources
- **Nightly Chainguard Workflow:** Fixed `/usr/bin/python: can't open file '//python'` error caused by Chainguard entrypoint doubling
- **SSL Certificate Handling:** Added intentional nosemgrep directive with justification for compatibility with self-signed certificates
- **Documentation Accuracy:** Corrected 50+ port references (3000 → 8888), removed fabricated features (HPA, non-existent env vars), verified all claims against implementation
- **API Response Format:** Clarified ExternalDNS webhook media type and endpoint behaviors across all docs
- **Health Check Documentation:** Corrected endpoint paths and port numbers in Kubernetes probe examples
- **Server Thread Exception Handling:** Changed from Exception to BaseException to properly handle SystemExit

**Security:**

- **Private CA Support:** Seamless HTTPS deployment with private certificate authorities (self-signed, internal PKI)
- **Semgrep Integration:** Multi-pattern security scanning for Python vulnerabilities
- **Error Sanitization:** Prevents password, token, and path disclosure in error responses to clients
- **Input Validation:** RFC 1035/1123 DNS name validation, IPv4/IPv6 address validation, TTL range enforcement
- **Rate Limiting:** Token bucket algorithm with configurable sustained rate (1000 req/min default)
- **Request Size Limits:** 1MB default payload size limit with HTTP 413 response on excess
- **Container Security:** Chainguard non-root user (UID 65532), read-only filesystem capable, multi-arch support (AMD64, ARM64)

**Documentation:**

- ✅ ARCHITECTURE.md - Mermaid diagrams, port/endpoint accuracy, logging format
- ✅ API.md - Complete endpoint reference, response formats, error handling
- ✅ PERFORMANCE.md - Async-first design, connection pooling, resource limits (100m-500m CPU, 128Mi-512Mi memory)
- ✅ MONITORING.md - Structured logging, health checks, troubleshooting guide
- ✅ DEVELOPMENT.md - Port 8888 main API + 8080 health, debugging config, project structure
- ✅ CICD_SECURITY.md - Accurate workflow table, security tools (CodeQL, Trivy, Semgrep), no false references
- ✅ CREDENTIALS_SETUP.md - Step-by-step Technitium user setup, permission requirements, Kubernetes secrets
- ✅ SECURITY.md - Semgrep scanning, no Bandit compatibility notes, security measures overview

**Test Coverage:**

- 176 comprehensive tests across all modules
- 99% code coverage (933/941 lines)
- pytest-asyncio for async test support
- pytest-mock for external call mocking
- Fixtures for test isolation and repeatability

**Performance & Reliability:**

- Async-first architecture with non-blocking I/O
- HTTP connection pooling to Technitium (httpx.AsyncClient)
- Graceful shutdown with signal handling (SIGTERM/SIGINT)
- Automatic token renewal (20-minute intervals)
- Exponential backoff retry logic for transient failures

## [0.1.0] - 2025-01-XX

**Added:**

- Initial release
- Basic ExternalDNS webhook functionality
- Technitium DNS integration
