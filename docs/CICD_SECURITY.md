# CI/CD and Security Overview

This project implements enterprise-grade CI/CD pipelines with comprehensive security scanning, automated testing, and CVE remediation through GitHub Actions workflows.

## Workflow Summary

| Workflow | File | Triggers | Purpose |
| ---------- | ------ | ---------- | --------- |
| CI | `.github/workflows/ci.yml` | Push to any branch without an open PR; PR to any branch | Lints (Ruff), type-checks (mypy, pyright), runs tests with coverage validation (95% minimum), uploads coverage to Codecov, builds multi-arch Docker images for commit, validates `pylock.toml` is in sync with `pyproject.toml` |
| Security Scanning | `.github/workflows/security.yml` | Daily at midnight UTC, PRs, pushes to non-`main` branches without an open PR, and manual | Checks Python code and dependencies, and gates PR images |
| Scheduled Security Rebuild | `.github/workflows/scheduled-rebuild.yml` | Daily at 02:00 UTC on `main`; manual on `main` or `develop` | Builds and scans an isolated multi-architecture candidate, uses Copa to apply available Debian package updates, and rescans if Copa patches the image. The Kind integration suite runs before promotion of mutable tags on `main`. |
| Release | `.github/workflows/release.yml` | Push to `main` that changes `pyproject.toml`; manual | Validates the requested version, creates the Git tag and GitHub release, builds multi-platform Docker images, publishes to GHCR, generates an SBOM, and signs the image |

## Security Scanning Strategy

The project employs **multi-layer security scanning** for defense-in-depth:

### Active Security Tools

1. **Ruff** (CI) - Fast Python linter with security-aware rules (format, lint, unused imports)
2. **mypy & pyright** (CI) - Strict static type checking to catch type-related bugs
3. **CodeQL** (Security.yml) - Semantic code analysis for security vulnerabilities in Python
4. **Snyk** - Container image and Python dependency scanning
5. **SonarCloud** (CI) - Code quality and security-hotspot analysis; runs on `main` pushes and decorates same-repo pull requests
6. **Docker build provenance** (CI & Release) - SBOM and attestation generation with build signatures

### Code & Supply Chain Security

- **CodeQL** - GitHub's semantic analysis tool for security vulnerabilities
- **Snyk scanning** - One scan of the PR image emits JSON for the gate and SARIF for run artifacts. Syft generates the SBOM from the same image.
- **Snyk gate policy** - Only fixable critical/high findings block the pipeline; unfixable findings are listed in the job summary for triage
- **Nightly remediation gate** - The rebuild reuses the candidate's Snyk reports when there are no package updates. When Copa patches the candidate, Snyk rescans both architectures. Both final architecture reports must contain a valid vulnerabilities array and no scan error. Fixable high or critical findings block the rebuild, and Kind integration tests must pass before promotion.
- **Build provenance** - SBOM generation and artifact attestation tracking in Release workflow
- **GitHub Dependabot** - Automated dependency update suggestions (not automated in CI)

After a successful promotion on `main`, the security rebuild uploads the SARIF reports from the scans that supplied the vulnerability gate for both architectures. PR, rebuild candidate, and release scan reports are available in their run artifacts.

## Required Secrets & Configuration

Core CI/CD runs on GitHub's built-in features plus a small set of repository secrets for the hardened-image and quality-scan integrations:

### Repository Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `DOCKER_HUB_RO_USER` / `DOCKER_HUB_RO_PAT` | Yes | Read-only Docker Hub credentials for pulling the `dhi.io` Hardened Python base image (CI builds, scheduled rebuilds, release builds) |
| `SONAR_TOKEN` | Recommended | SonarCloud analysis on `main` pushes and PR-decorating scans (steps skip gracefully when unset) |
| `SNYK_TOKEN` | Recommended | Snyk container and dependency scanning |

### GitHub Actions Built-ins

- **GITHUB_TOKEN** - Automatically provided by GitHub Actions
  - Used for container registry push (`ghcr.io/${{ github.repository }}`)
  - Used for CodeQL analysis and SARIF upload
  - Scope: `packages: write`, `security-events: write`, `contents: read`

### Optional Enhancements

- **Repository branch protection rules** - Require CI workflow success before merging to `main`
- **GitHub Security settings** - Enable "Require status checks to pass before merging"
- **Dependabot alerts** - Enable in repository settings for automated vulnerability notifications

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

**Note:** `make all` runs the full CI pipeline including code analysis. Security scanning via GitHub Actions (CodeQL, Snyk) runs separately in automated workflows.

## Contributing to CI/CD

When adding new workflows or modifying existing ones:

1. Create feature branch and PR
2. Verify all workflow runs complete successfully
3. Document any new secrets or configuration
4. Update this file with workflow changes
5. Merge to `develop` first, then promote to `main`
