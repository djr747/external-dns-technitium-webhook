# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2025-11-09

### Changed
- **CI/CD Pipeline:** Major overhaul of GitHub Actions workflow for improved reliability and efficiency
  - Streamlined multi-architecture Docker builds with artifact-based job separation
  - Added Chainguard Python version guard to prevent drift between test matrix and base image
  - Implemented atomic manifest push after successful testing
  - Enhanced branch tagging and artifact handling for better CI performance
  - Fixed local tag lookup and verification steps
  - Added comprehensive error handling and cleanup in CI jobs

## [0.2.9] - 2025-11-03

### Dependencies
- Bump fastapi from 0.120.4 to 0.121.0 - adds support for dependencies with scopes and scope="request" for early-exit dependencies

### Documentation
- Add comprehensive release workflow documentation in `docs/RELEASE.md`
- Update `copilot-instructions.md` with detailed release workflow section
- Document production vs development dependency separation and automated release triggering

## [0.2.8] - 2025-11-03

### Fixed
- **Release Notes:** Corrected base image references in release notes and OCI labels from incorrect "Red Hat UBI10" to actual "Chainguard Python"

## [0.2.7] - 2025-11-03

### Fixed
- **Release Automation:** Fixed SBOM and security scan upload in release workflow - added `contents:write` permission to container build job and switched from `softprops/action-gh-release` to `gh release upload` CLI for more reliable asset uploads

## [0.2.6] - 2025-11-02

### Changed
- **Release Automation:** Consolidated all release logic into single `release.yml` workflow - removed `auto-tag-on-main.yml`. Workflow now triggers on `pyproject.toml` changes to main, creates git tag, creates GitHub release, then builds/publishes container.

## [0.2.5] - 2025-11-02

### Fixed
- **Release Automation:** Simplified release workflow to use GitHub's standard tagging pattern - auto-tag creates tags only, GitHub automatically creates releases from tags, release.yml triggers on release published event (reliable webhook pattern)

## [0.2.4] - 2025-11-02

### Fixed
- **Release Workflow Trigger:** Changed trigger from `release: [published]` to `release: [created, published]` to properly handle releases created via GitHub API (API-created releases emit `created` event, not `published`)

## [0.2.3] - 2025-11-02

### Fixed
- **Auto-Tag Workflow:** Added git user configuration for tag creation in GitHub Actions runner

## [0.2.2] - 2025-11-02

### Fixed
- **Auto-Tag Workflow:** Replaced deprecated `actions/create-release@v1` with `actions/github-script@v7` for proper git tag and GitHub Release creation
- **Workflow Trigger:** Added `workflow_dispatch` trigger to allow manual testing of release automation

## [0.2.1] - 2025-11-02

### Added
- **Version-Driven Release Automation:** Implemented `pyproject.toml` as single source of truth for version control
- **Auto-Tag Workflow:** New `auto-tag-on-main.yml` that automatically creates git tags and GitHub releases when version bumps on main
- **CHANGELOG Validation:** Release workflow validates CHANGELOG.md has been updated before creating release (prevents undocumented releases)
- **Dependabot Integration:** Automatic patch releases when Dependabot merges dependency updates with version bumps

### Changed
- **Release Process:** Simplified from complex tag-based triggers to clean version-driven automation
- **Release Documentation:** Updated CONTRIBUTING.md and copilot-instructions.md with complete release workflow

## [0.2.0] - 2025-11-02

### Added
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

### Changed
- **Port Configuration:** Clarified main API runs on port 8888, health checks on port 8080 (separate thread)
- **Chainguard Python:** Updated to Chainguard Python latest (3.13) with zero-CVE base image
- **CI/CD Tools:** Migrated from Bandit to Semgrep for pattern-based security scanning
- **Logging Format:** Structured logs unified across all sources (app, uvicorn, httpx) using External-DNS format with ISO 8601 timestamps and key-value pairs
- **Makefile:** Added `security` target to `make all` for comprehensive CI pipeline validation
- **Python Version:** datetime.utc → UTC import for Python 3.13+ compatibility
- **Docker Ports:** Updated `make docker-run` from port 3000 to 8888/8080
- **Dependabot Configuration:** Updated from Bandit to Semgrep for security scans

### Fixed
- **Logging Implementation:** Applied StructuredFormatter to uvicorn, httpx, and application loggers for consistent External-DNS format across all sources
- **Nightly Chainguard Workflow:** Fixed `/usr/bin/python: can't open file '//python'` error caused by Chainguard entrypoint doubling
- **SSL Certificate Handling:** Added intentional nosemgrep directive with justification for compatibility with self-signed certificates
- **Documentation Accuracy:** Corrected 50+ port references (3000 → 8888), removed fabricated features (HPA, non-existent env vars), verified all claims against implementation
- **API Response Format:** Clarified ExternalDNS webhook media type and endpoint behaviors across all docs
- **Health Check Documentation:** Corrected endpoint paths and port numbers in Kubernetes probe examples
- **Server Thread Exception Handling:** Changed from Exception to BaseException to properly handle SystemExit

### Security
- **Private CA Support:** Seamless HTTPS deployment with private certificate authorities (self-signed, internal PKI)
- **Semgrep Integration:** Multi-pattern security scanning for Python vulnerabilities
- **Error Sanitization:** Prevents password, token, and path disclosure in error responses to clients
- **Input Validation:** RFC 1035/1123 DNS name validation, IPv4/IPv6 address validation, TTL range enforcement
- **Rate Limiting:** Token bucket algorithm with configurable sustained rate (1000 req/min default)
- **Request Size Limits:** 1MB default payload size limit with HTTP 413 response on excess
- **Container Security:** Chainguard non-root user (UID 65532), read-only filesystem capable, multi-arch support (AMD64, ARM64)

### Documentation
- ✅ ARCHITECTURE.md - Mermaid diagrams, port/endpoint accuracy, logging format
- ✅ API.md - Complete endpoint reference, response formats, error handling
- ✅ PERFORMANCE.md - Async-first design, connection pooling, resource limits (100m-500m CPU, 128Mi-512Mi memory)
- ✅ MONITORING.md - Structured logging, health checks, troubleshooting guide
- ✅ DEVELOPMENT.md - Port 8888 main API + 8080 health, debugging config, project structure
- ✅ CICD_SECURITY.md - Accurate workflow table, security tools (CodeQL, Trivy, Semgrep), no false references
- ✅ CREDENTIALS_SETUP.md - Step-by-step Technitium user setup, permission requirements, Kubernetes secrets
- ✅ SECURITY.md - Semgrep scanning, no Bandit compatibility notes, security measures overview

### Test Coverage
- 176 comprehensive tests across all modules
- 99% code coverage (933/941 lines)
- pytest-asyncio for async test support
- pytest-mock for external call mocking
- Fixtures for test isolation and repeatability

### Performance & Reliability
- Async-first architecture with non-blocking I/O
- HTTP connection pooling to Technitium (httpx.AsyncClient)
- Graceful shutdown with signal handling (SIGTERM/SIGINT)
- Automatic token renewal (20-minute intervals)
- Exponential backoff retry logic for transient failures

## [0.1.0] - 2025-01-XX

### Added
- Initial release
- Basic ExternalDNS webhook functionality
- Technitium DNS integration

[Unreleased]: https://github.com/djr747/external-dns-technitium-webhook/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/djr747/external-dns-technitium-webhook/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/djr747/external-dns-technitium-webhook/releases/tag/v0.1.0
