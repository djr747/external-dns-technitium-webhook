# CI/CD and Security Overview

This project implements enterprise-grade CI/CD pipelines with comprehensive security scanning, automated testing, and CVE remediation through GitHub Actions workflows.

## Workflow Summary

| Workflow | File | Triggers | Purpose |
|----------|------|----------|---------|
| CI | `.github/workflows/ci.yml` | Push to any branch; PR to `main`/`develop` | Lints (Ruff), type-checks (mypy, pyright), runs tests with coverage validation (95% minimum), uploads coverage to Codecov, builds multi-arch Docker images for commit, validates Python version matches Chainguard base |
| Security Scanning | `.github/workflows/security.yml` | Daily schedule (UTC midnight); push to `main`/`develop`; PR to `main`; manual | CodeQL semantic code analysis, Trivy container vulnerability scan (SARIF + JSON), generates Trivy summary, uploads to GitHub Security tab |
| Scheduled Security Rebuild | `.github/workflows/scheduled-rebuild.yml` | Mondays 02:00 UTC; manual | Rebuilds container on latest Chainguard Python base, runs Trivy scan, opens GitHub issue for critical CVEs |
| Release | `.github/workflows/release.yml` | Semantic version tags (semver); manual | Validates semantic version tag, builds multi-platform Docker images, publishes to GHCR, generates SBOMs and provenance attestations, verifies attestation signatures |
| Nightly Chainguard Version | `.github/workflows/nightly-chainguard-python-version.yml` | Daily schedule; manual | Checks for newer Chainguard Python versions, updates Dockerfile if available, creates PR for review |

## Security Scanning Strategy

The project employs **multi-layer security scanning** for defense-in-depth:

### Active Security Tools

1. **Ruff** (CI) - Fast Python linter with security-aware rules (format, lint, unused imports)
2. **mypy & pyright** (CI) - Strict static type checking to catch type-related bugs
3. **CodeQL** (Security.yml) - Semantic code analysis for security vulnerabilities in Python
4. **Trivy** (Security.yml & Release.yml) - Container image and SBOM vulnerability scanner for CVEs
5. **Docker build provenance** (CI & Release) - SBOM and attestation generation with build signatures

### Code & Supply Chain Security

- **CodeQL** - GitHub's semantic analysis tool for security vulnerabilities
- **Trivy scanning** - Multi-stage: SARIF format for GitHub Security integration + JSON for detailed analysis
- **Build provenance** - SBOM generation and artifact attestation tracking in Release workflow
- **GitHub Dependabot** - Automated dependency update suggestions (not automated in CI)

Trivy scans upload SARIF results to GitHub's Security tab for visibility and tracking.

## Required Secrets & Configuration

The CI/CD workflows use GitHub's built-in features and do not require additional secrets to be configured:

### GitHub Actions Built-ins

- **GITHUB_TOKEN** - Automatically provided by GitHub Actions
  - Used for container registry push (`ghcr.io/${{ github.repository }}`)
  - Used for CodeQL analysis and SARIF upload
  - Scope: `packages: write`, `security-events: write`, `contents: read`

### Optional Enhancements

- **Repository branch protection rules** - Require CI workflow success before merging to `main`
- **GitHub Security settings** - Enable "Require status checks to pass before merging"
- **Dependabot alerts** - Enable in repository settings for automated vulnerability notifications

No additional tokens or API credentials are required for core CI/CD operation.

## Local CI Simulation

Test your changes match CI requirements before pushing:

```bash
make all        # Run format, lint, type-check, test, security (full CI pipeline)
make format     # Ruff format code
make lint       # Ruff check + pyright
make type-check # mypy + pyright strict
make test       # pytest
make test-cov   # pytest with coverage report (HTML + terminal)
make security   # Semgrep code scan
```

**Note:** `make all` runs the full CI pipeline including code analysis. Security scanning via GitHub Actions (CodeQL, Trivy) runs separately in automated workflows.

## Contributing to CI/CD

When adding new workflows or modifying existing ones:

1. Create feature branch and PR
2. Verify all workflow runs complete successfully
3. Document any new secrets or configuration
4. Update this file with workflow changes
5. Merge to `develop` first, then promote to `main`
