# GitHub Actions Workflows

This repository uses a comprehensive CI/CD pipeline with security best practices, automated testing, and CVE scanning.

## 📋 Workflows Overview

### 🔄 CI Pipeline (`ci.yml`)

**Triggers:** Pushes to branches without an open PR, and pull requests targeting any branch

**Jobs:**
- **Lint**: Code quality checks with Ruff and pyright
- **Type Check**: Type checking with mypy (strict mode) and pyright
- **Test**: Python 3.13 with 95% coverage requirement (actual coverage: 99%)
- **Security Python**: Semgrep and pip-audit CVE scanning
- **Snyk Security**: Vulnerability detection with Snyk
  - **Docker Build**: Container build and multi-scanner security check (Snyk)

**Key Features:**
- Single version Python testing (3.13)
- Coverage artifact upload for manual inspection
- SARIF upload to GitHub Security tab
- Parallel security scanning

### 🐳 Docker Build (`docker.yml`)

**Triggers:** Push to main, tags, PR, manual dispatch

**Jobs:**
- **Build and Push**: Multi-arch (amd64, arm64) container builds
 - **Vulnerability Scan**: Snyk container scanning
- **Sign Image**: Cosign image signing for releases

**Key Features:**
- Multi-platform builds (AMD64, ARM64)
- SBOM generation (SPDX format)
- Provenance attestation
- Image signing with Cosign
- Semantic versioning tags
- GitHub Container Registry (ghcr.io)

### 🔒 Security Scanning (`security.yml`)

**Triggers:** Daily (midnight UTC), pushes to non-`main` branches without an open PR, pull requests targeting any branch, manual

**Jobs:**
- **CodeQL Analysis**: GitHub's semantic code analysis
 - **Container Scan (Snyk)**: Container vulnerability scanning
- **Dependency Scan**: pip-audit for Python CVEs
- **Code Scan**: Bandit and Semgrep static analysis
- **Snyk Security**: Multi-layer vulnerability detection
- **SBOM Generation**: Syft SBOM + Grype analysis
- **Security Summary**: Aggregated report

**Key Features:**
- 7 different security tools
- SARIF uploads to GitHub Security tab
- Artifact retention (90 days)
- Comprehensive summary reports

### 🔄 Scheduled Rebuild (`scheduled-rebuild.yml`)

**Triggers:** Daily at 02:00 UTC, manual dispatch

**Purpose:** Automated security patching from base image updates

**Jobs:**
- **Check for Updates**: Inspect the Chainguard Python base image
- **Rebuild Image**: Force a multi-architecture rebuild with the latest base-image patches
- **Vulnerability Scan**: Post-rebuild security check
- **Snyk Monitor**: Track vulnerabilities over time

**Key Features:**
- Automatic daily rebuilds for CVE patching
- No-cache builds to pull latest base images
- Issue creation for critical vulnerabilities
- Updates the mutable `latest` and `latest-patched` tags; release-version tags are not retagged
- Vulnerability trend tracking

### 🚀 Release (`release.yml`)

**Triggers:** Version tags (v*.*.*), manual dispatch

**Jobs:**
- **Validate Version**: Semantic version validation
- **Create Release**: GitHub release with changelog
- **Build Container**: Multi-arch container release with signing
- **Update Changelog**: Automatic CHANGELOG.md updates

**Key Features:**
- Semantic versioning enforcement
- Automated changelog generation
- SBOM attached to releases
- Image signing for released versions
- Multi-platform container images
- GitHub Container Registry (ghcr.io) publishing

## 🔐 Security Features

### CVE Scanning

The pipeline includes multiple layers of CVE detection:

1. **Snyk** - Container, code, and dependency vulnerability scanning
2. **pip-audit** - Python dependency CVE database
3. **Grype** - SBOM-based vulnerability detection
4. **GitHub Dependabot** - Automated dependency updates

### Secret Protection

- **GitHub Secret Scanning**: Native GitHub protection
- **Snyk Secrets**: Container image secret detection

### Code Security

- **CodeQL**: Semantic code analysis (security-extended queries)
- **Bandit**: Python security linter
- **Semgrep**: Pattern-based security rules
- **Snyk Code**: AI-powered vulnerability detection

## 📊 Reporting and Compliance

### Security Tab Integration

All security findings are uploaded to GitHub Security tab via SARIF:
- Navigate to **Security** → **Code scanning alerts**
- View aggregated results from all scanners
- Track remediation over time


Security reports retained for 90 days:
### Artifacts
- Snyk JSON/SARIF reports
- pip-audit CVE lists
- Bandit security findings
- SBOM files (SPDX + CycloneDX)

### Summary Reports

GitHub Actions Summary provides:
- Vulnerability counts by severity
- Test coverage metrics
- Build status and metadata

## 🔧 Required Secrets

Add these secrets to your repository settings:

| Secret | Required | Purpose |
|--------|----------|---------|
| `SNYK_TOKEN` | Recommended | Snyk security scanning |

**Note:** No PyPI token needed - this project uses container deployment only.

## 📈 Versioning Strategy

### Version Tags

- **Release**: `v1.2.3` (semantic versioning)
- **Pre-release**: `v1.2.3-beta.1`, `v1.2.3-rc.1`

### Container Tags

Release builds create `1.2.3`, `1.2`, and `1` tags. The exact version tag is the stable release-specific image; the minor and major tags move only when a newer matching release is published.

The scheduled security rebuild publishes `latest`, `latest-patched`, and a dated `latest-patched-<YYYYMMDD>` tag for both `linux/amd64` and `linux/arm64`. The first two are mutable and rebuilt daily from `main` to incorporate the latest Chainguard base-image patches. They do not retag release-version images.

Pin an exact version tag (for example, `1.2.3`) or a digest for reproducible production deployments.

### Change Tracking

- **Automated changelog generation** from git commits
- **Semantic commit messages** recommended:
  - `feat:` - New features
  - `fix:` - Bug fixes
  - `sec:` - Security updates
  - `docs:` - Documentation
  - `chore:` - Maintenance

## 🚦 Workflow Status Badges

Add to README.md:

You can add these badges to your README:

```markdown
![CI](https://github.com/djr747/external-dns-technitium-webhook/workflows/CI/badge.svg)
![Security](https://github.com/djr747/external-dns-technitium-webhook/workflows/Security%20Scanning/badge.svg)
![Docker](https://github.com/djr747/external-dns-technitium-webhook/workflows/Docker%20Build%20and%20Push/badge.svg)
```

## 🔄 Scheduled Jobs

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| Security Scanning | Daily 00:00 UTC | Security audit |
| Scheduled Rebuild | Daily 02:00 UTC | Rebuild `latest`/`latest-patched` with base-image CVE patches |

## 🎯 Best Practices Implemented

### Testing
- ✅ Python 3.13 testing
- ✅ Minimum 95% code coverage requirement (actual coverage: 99%)
- ✅ Type checking with mypy (strict mode) and pyright
- ✅ Code formatting and linting with Ruff

### Security
- ✅ Multiple CVE scanners for redundancy
- ✅ SARIF upload to GitHub Security
- ✅ Weekly security audits
- ✅ Automatic base image patching
- ✅ Secret scanning in git history
- ✅ SBOM generation and analysis
- ✅ Image signing with Cosign

### Container
- ✅ Multi-architecture builds (AMD64, ARM64)
- ✅ Chainguard minimal Python base image (low CVE footprint)
- ✅ Layer caching for fast builds
- ✅ Provenance and SBOM attestation
- ✅ Non-root user execution
- ✅ Minimal attack surface

### Release
- ✅ Semantic versioning validation
- ✅ Automated changelog generation
- ✅ GitHub release automation
- ✅ Container image signing with Cosign
- ✅ SBOM attached to releases
- ✅ Multi-platform container deployment

## 🐛 Troubleshooting

### Snyk Token Missing
If you don't have Snyk:
1. Sign up at https://snyk.io
2. Generate API token
3. Add as `SNYK_TOKEN` secret
4. Or disable Snyk jobs in workflows

### Build Failures
- Check **Actions** tab for detailed logs
- Review **Security** tab for vulnerability blocks
- Ensure all required secrets are configured

### Coverage Failures
Tests must maintain 95% coverage minimum:
```bash
pytest --cov=external_dns_technitium_webhook --cov-fail-under=95
```

Current project coverage: 99% (933/941 lines)

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Snyk Documentation](https://docs.snyk.io)
 
- [Cosign Documentation](https://docs.sigstore.dev/cosign/overview/)
- [SBOM Standards](https://www.cisa.gov/sbom)
