# CI/CD and Security Overview# CI/CD and Security Summary



This project relies on GitHub Actions for builds, tests, scans, and releases. The workflows favor fast feedback for pull requests and continuous security posture for the main branch.## Overview



## Workflow SummaryThis project implements enterprise-grade CI/CD pipelines with comprehensive security scanning, automated testing, and CVE remediation through automated rebuilds.



| Workflow | File | Trigger Highlights | What It Does |## Key Features

| --- | --- | --- | --- |

| CI | `.github/workflows/ci.yml` | Push/PR to `main` or `develop` | Lints, type-checks, runs the Python test matrix, generates coverage artifacts, runs Bandit + pip-audit, executes Snyk code scan, and validates the container with Trivy + Snyk. |### 🔒 Multi-Layer Security Scanning

| Docker Build & Push | `.github/workflows/docker.yml` | Push/PR to `main`, semver tags, manual | Builds multi-arch images, publishes to GHCR, produces SBOMs, and runs Trivy + Snyk container scans (publishes SARIF). |

| Security Scanning | `.github/workflows/security.yml` | Weekly schedule, push/PR, manual | Runs CodeQL, Trivy, pip-audit, Bandit, Semgrep, Snyk, and SBOM/Grype analysis with a consolidated summary. |**5 CVE Detection Tools:**

| Scheduled Security Rebuild | `.github/workflows/scheduled-rebuild.yml` | Mondays 02:00 UTC, manual | Rebuilds the container on the latest UBI base image, scans with Trivy + Snyk, and reports vulnerability counts (opens an issue for critical findings). |1. **Trivy** - Container vulnerability scanner

| Release | `.github/workflows/release.yml` | Semantic version tags, manual | Validates the tag, builds and signs multi-arch images, generates SBOMs, runs Trivy scans, and publishes GitHub release notes + changelog entry. |2. **Snyk** - Multi-layer security platform

3. **pip-audit** - Python dependency CVE checker

## Security Tooling4. **Grype** - SBOM-based vulnerability scanner

5. **GitHub Dependabot** - Automated dependency updates

- **Static Analysis & Dependency Scanning:** Ruff, mypy, pip-audit, Bandit, Semgrep

- **Container & Supply Chain:** Trivy (image + SBOM), Snyk (code + container), Grype, Syft SBOM, Cosign signing**Code Security:**

- **CodeQL:** Full repository semantic analysis on a weekly cadence and for each push to `main`- CodeQL (GitHub's semantic analysis)

- **Scheduled Patch Builds:** Weekly rebuild pulls the latest Red Hat UBI 10 base image and re-runs security scanners- Bandit (Python security linter)

- Semgrep (pattern-based security)

All scanners upload SARIF results to the GitHub Security tab and store JSON/SBOM artifacts for 90 days.



## Required Secrets & Configuration### 🔄 Automated Patching



| Secret | Purpose |**Weekly Scheduled Rebuilds** (Monday 2 AM UTC):

| --- | --- |- Automatic detection of UBI10 base image updates

| `SNYK_TOKEN` | Enables Snyk scans in CI, Docker, security, and scheduled rebuild workflows |- Force rebuild to pull latest security patches

- Post-build vulnerability scanning

No additional secrets are needed for the default pipelines; GitHub’s built-in `GITHUB_TOKEN` handles pushing images to GHCR and posting releases.- Issue creation for critical CVEs

- Vulnerability trend tracking

## Maintaining Pipeline Health

### 🐳 Container Security

1. **Keep `SNYK_TOKEN` current.** Expired tokens skip scans and reduce coverage.

2. **Monitor the Security tab.** SARIF uploads from CodeQL, Trivy, Bandit, Semgrep, and Snyk appear there with remediation guidance.**Red Hat UBI10 Base Images:**

3. **Review weekly rebuild results.** Critical findings automatically raise a GitHub Issue; resolve them or pause the release pipeline if necessary.- Vendor-supported CVE remediation

4. **Validate before release tags.** Run `make lint`, `make type-check`, and `make test-cov` locally to mirror CI stages.- Enterprise-grade security updates

- Python 3.12 runtime

For detailed job steps or to trigger a manual run, open the GitHub Actions tab and select the desired workflow.- Multi-stage build optimization


**Security Features:**
- SBOM generation (SPDX + CycloneDX)
- Image signing with Cosign
- Provenance attestation
- Non-root execution (UID 1000)
- Multi-arch builds (AMD64, ARM64)

### 🧪 Testing

**Python Version Matrix:**
- Python 3.12, 3.13
- 95% minimum code coverage
- Type checking with mypy and pyright
- Code formatting with Ruff

### 📦 Release Management

**Semantic Versioning:**
- Automated version validation
- Changelog generation from commits
- GitHub release creation
- PyPI package publishing
- Container image signing

**Tagging Strategy:**
```
v1.2.3              # Specific version
v1.2                # Minor version
v1                  # Major version
latest              # Latest stable
latest-patched      # Weekly security rebuild
main-sha123         # Branch + commit
2024-01-15-sha123   # Date + commit
```

## Workflows

### CI Pipeline
**Runs on:** Every push, PR
- Linting and type checking
- Multi-version testing
- Security scanning (Bandit, pip-audit, Snyk)
- Docker build and scan

### Security Scanning
**Runs on:** Weekly (Sunday), push to main, PRs
- CodeQL analysis
- Container scanning (Trivy)
- Dependency CVE check
- Code security (Bandit, Semgrep)
- Secret scanning
- SBOM generation and analysis

### Docker Build & Push
**Runs on:** Push to main, tags, PRs
- Multi-arch container builds
- SBOM generation
- Vulnerability scanning
- Image signing (releases only)

### Scheduled Rebuild
**Runs on:** Weekly (Monday 2 AM UTC)
- Check for base image updates
- Rebuild with latest patches
- Scan for vulnerabilities
- Create issues for critical CVEs

### Release
**Runs on:** Version tags (v*.*.*)
- Version validation
- Changelog generation
- Container release (multi-arch)
- SBOM attachment
- Image signing

## Security Reporting

### GitHub Security Tab
All findings uploaded via SARIF:
- Navigate to **Security** → **Code scanning**
- View consolidated alerts from all scanners
- Track remediation status

### Artifact Retention
90-day retention for:
- Vulnerability scan reports (JSON/SARIF)
- SBOM files
- Security analysis results
- Coverage reports

## Required Configuration

### Repository Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `SNYK_TOKEN` | Recommended | Enables Snyk code and container scans |

> **Note:** This project uses container deployment only. No PyPI token needed.

### Branch Protection

Recommended settings for `main` branch:
- Require PR reviews
- Require status checks (CI, Security)
- Require up-to-date branches
- No force pushes
- Include administrators

## Compliance

### Supply Chain Security
- ✅ SBOM generation (SPDX format)
- ✅ Provenance attestation
- ✅ Image signing (Sigstore Cosign)
- ✅ Dependency tracking
- ✅ Automated vulnerability scanning

### CVE Remediation
- ✅ Weekly automated rebuilds
- ✅ Multiple scanner redundancy
- ✅ Vendor-supported base images (Red Hat UBI10)
- ✅ Automated issue creation
- ✅ Vulnerability trend tracking

### Best Practices
- ✅ Multi-version testing
- ✅ Type safety enforcement
- ✅ Code coverage requirements (80%)
- ✅ Secret scanning
- ✅ Non-root containers
- ✅ Multi-architecture support

## Monitoring and Alerts

### Issue Creation
Automated issue creation for:
- Critical vulnerabilities in scheduled rebuilds
- Failed security scans
- Coverage drops below threshold

### Summary Reports
GitHub Actions Summary includes:
- Vulnerability counts by severity
- Test results and coverage
- Build status and metadata
- Security scan overview

## Development Workflow

### Making Changes
1. Create feature branch
2. Make changes with tests
3. Push triggers CI pipeline
4. Security scans run automatically
5. PR review with status checks
6. Merge to main

### Creating Release
1. Tag version: `git tag v1.2.3`
2. Push tag: `git push origin v1.2.3`
3. Automatic release workflow:
   - Validates version
   - Generates changelog
   - Builds Python package
   - Builds container images
   - Publishes to PyPI & GHCR
   - Signs images
   - Creates GitHub release

### Checking Security Status
1. Go to **Security** tab
2. View **Code scanning alerts**
3. Review findings by severity
4. Check **Dependabot alerts**
5. Review artifact reports in Actions

## Maintenance

### Weekly Automated Tasks
- **Sunday 00:00 UTC**: Full security scan
- **Monday 02:00 UTC**: Rebuild for patches

### Manual Triggers
All workflows support `workflow_dispatch` for manual execution:
1. Go to **Actions** tab
2. Select workflow
3. Click **Run workflow**
4. Choose branch and inputs

## Metrics and Reporting

### Key Metrics Tracked
- Test coverage percentage
- Vulnerability count by severity
- Build success rate
- Time to patch CVEs
- SBOM completeness

### Available Reports
- Trivy JSON vulnerability reports
- Snyk security analysis
- pip-audit CVE findings
- Bandit security issues
- SBOM files (SPDX/CycloneDX)
- Coverage HTML reports

## Future Enhancements

Potential additions:
- SLSA provenance level 3
- Fuzzing integration
- Performance benchmarking
- License compliance scanning
- Dependency review automation
- Container image optimization metrics

## Support

For issues or questions:
1. Check [WORKFLOWS.md](../.github/WORKFLOWS.md)
2. Review Actions logs
3. Check Security tab alerts
4. Open GitHub issue
