# CI/CD and Security Overview

This project implements enterprise-grade CI/CD pipelines with comprehensive security scanning, automated testing, and CVE remediation through GitHub Actions workflows.

## Workflow Summary

| Workflow | File | Triggers | Purpose |
|----------|------|----------|---------|
| CI | `.github/workflows/ci.yml` | Push/PR to `main` or `develop` | Lints, type-checks, runs tests, generates coverage, dependency scanning (pip-audit), code analysis (Bandit, Semgrep), and container validation (Trivy, Snyk) |
| Docker Build & Push | `.github/workflows/docker.yml` | Push/PR to `main`, semver tags, manual | Builds multi-platform images, publishes to GHCR, generates SBOMs, runs Trivy and Snyk scans, publishes SARIF results |
| Security Scanning | `.github/workflows/security.yml` | Weekly schedule, push/PR, manual | CodeQL semantic analysis, Trivy container scan, pip-audit, Bandit, Semgrep, Snyk, SBOM analysis with Grype |
| Scheduled Security Rebuild | `.github/workflows/scheduled-rebuild.yml` | Mondays 02:00 UTC, manual | Rebuilds container on latest Red Hat UBI base, runs security scans, opens issue for critical CVEs |
| Release | `.github/workflows/release.yml` | Semantic version tags, manual | Validates tag, builds multi-arch images, signs with Cosign, generates SBOMs, publishes GitHub release with notes |

## Security Scanning Strategy

The project employs **5 CVE detection tools** for defense-in-depth:

1. **Trivy** - Container image and SBOM vulnerability scanner
2. **Snyk** - Multi-layer vulnerability detection (code, dependencies, containers)
3. **pip-audit** - Python package vulnerability checking
4. **Grype** - SBOM-based vulnerability analysis
5. **GitHub Dependabot** - Automated dependency update suggestions

### Code Security Tools

- **Ruff** - Fast Python linter and formatter
- **mypy** - Strict static type checking
- **Bandit** - Python security linter for common vulnerabilities
- **Semgrep** - Pattern-based security vulnerability detection
- **CodeQL** - Semantic code analysis for security vulnerabilities

All scanners upload SARIF results to GitHub's Security tab for visibility and tracking.

## Required Secrets & Configuration

These secrets must be configured in GitHub repository settings for workflows to function:

### Container Registry
- `GHCR_TOKEN` - GitHub Container Registry token for pushing images (with `write:packages` scope)

### Security Scanning
- `SNYK_TOKEN` - Snyk API token for vulnerability scanning

### Code Signing
- `COSIGN_EXPERIMENTAL` - Set to `true` to use keyless Cosign signing with GitHub OIDC

## Local CI Simulation

Test your changes match CI requirements before pushing:

```bash
make all       # Run full CI pipeline
make lint      # Ruff format + check
make type-check # mypy + pyright strict
make test      # pytest with coverage
make security  # Semgrep scan
```

## Contributing to CI/CD

When adding new workflows or modifying existing ones:

1. Create feature branch and PR
2. Verify all workflow runs complete successfully
3. Document any new secrets or configuration
4. Update this file with workflow changes
5. Merge to `develop` first, then promote to `main`
