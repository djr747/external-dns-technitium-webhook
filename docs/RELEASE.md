# Release Workflow Guide

This document describes the complete release process for the ExternalDNS Technitium Webhook project.

## Overview

Releases are **automated and triggered by version changes** in `pyproject.toml`. The workflow detects when the `version =` line changes and automatically creates a release.

## Release Process

### Step 1: Update Version and CHANGELOG

When ready to release:

```bash
# 1. Update pyproject.toml version
# Current: version = "0.2.8"
# Change to: version = "0.2.9"

# 2. Update CHANGELOG.md with entry for new version
# Add section like:
# ## [0.2.9] - 2025-11-03
# ### Dependencies
# - Bump fastapi from 0.120.4 to 0.121.0

# 3. Commit both changes
git add pyproject.toml CHANGELOG.md
git commit -m "release: v0.2.9 - fastapi update"
```

### Step 2: Create Pull Request

Create a pull request to merge your changes to the `main` branch:

```bash
git push origin your-branch
gh pr create --base main --head your-branch \
  --title "release: v0.2.9" \
  --body "Release version 0.2.9 with fastapi update"
```

### Step 3: Merge and Watch Release Pipeline

When you **merge to main**, the release workflow automatically:

1. **check-version-changed**: Detects that `version =` line changed ✅
2. **validate-version**: Extracts version from pyproject.toml
3. **create-git-tag**: Creates git tag `v0.2.9` and pushes
4. **create-release**: Creates GitHub Release with auto-generated notes
5. **build-and-publish-container**:
   - Builds multi-arch Docker image (linux/amd64, linux/arm64)
   - Pushes to GitHub Container Registry
   - Generates and uploads SBOM (SPDX format)
   - Runs Trivy security scan
   - Signs image with Cosign
6. **update-changelog**: Updates CHANGELOG.md with release info

**Monitor the workflow:**
```bash
# Watch release.yml execution
gh run watch -R djr747/external-dns-technitium-webhook

# Or check release job details
gh run list --workflow=release.yml --limit=1
```

## Dependency Updates

### Production Dependencies (fastapi, uvicorn, httpx, pydantic)

When Dependabot creates a PR for production dependencies:

1. **Review the PR** for compatibility and test it
2. **Merge to main** (Dependabot typically targets main)
3. **The version detection will skip release** (no version change)
4. **Manually bump version** if you want to release:
   - Update `pyproject.toml` version
   - Update `CHANGELOG.md`
   - Commit and push to trigger release

### Development Dependencies (pytest, ruff, mypy, semgrep)

When dev/test dependencies update:

1. **Dependabot creates PR on `main` branch** automatically
2. **Merge directly to main** - no manual steps needed
3. **Version detection catches it**:
   - Checks if `version =` line changed
   - It didn't (only dependencies changed)
   - **Release is skipped automatically** ✅
4. **No git tag, no release, no container build**

This is the desired behavior - dev dependency changes don't trigger releases.

## Troubleshooting

### Release didn't trigger after merge

**Check:**
1. Was `version =` line changed in pyproject.toml?
2. Look at workflow run details in Actions tab
3. Check `check-version-changed` job output

### Container image not built

**Check:**
1. Is `build-and-publish-container` job running?
2. Check Docker registry push logs
3. Verify registry credentials are valid

### SBOM upload failed

**Solution:**
- Release.yml uses `gh release upload` with permissions
- If it fails, check `contents: write` permission is set in workflow

### Forgot to bump version

**Problem:** Merged changes but forgot to update `version =` in pyproject.toml

**Solution:**
1. Create a new commit on main bumping the version
2. Push to main
3. Release workflow will detect the version change and trigger
4. No need to revert - just fix forward

## Important Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Version source of truth (`version = "X.Y.Z"`) |
| `CHANGELOG.md` | Release notes and history |
| `.github/workflows/release.yml` | Release automation pipeline |
| `.github/dependabot.yml` | Dependency update configuration |

## Version Numbering

Use [Semantic Versioning](https://semver.org/):

- **MAJOR** (e.g., 1.0.0): Breaking changes
- **MINOR** (e.g., 0.2.0): New features, backward compatible
- **PATCH** (e.g., 0.2.9): Bug fixes, dependency updates

**Example progression:**
- 0.2.8 (last release)
- 0.2.9 (fastapi dependency bump)
- 0.3.0 (new feature added)
- 1.0.0 (breaking changes)

## Release Automation Details

### What Gets Pushed to Registry

When a release is created:

1. **Container Image**
   - Base: Chainguard Python (zero CVEs, daily updates)
   - Architecture: linux/amd64, linux/arm64
   - Tag: `vX.Y.Z` and `latest`
   - Signature: Cosigned with project key

2. **SBOM (Software Bill of Materials)**
   - Format: Anchore/SPDX
   - Includes: All Python dependencies with versions
   - Uploaded to GitHub Release

3. **Security Scan Results**
   - Trivy scan: Known CVE vulnerabilities
   - SARIF report: Upload to GitHub Security tab

4. **GitHub Release**
   - Auto-generated from CHANGELOG.md
   - Includes container image artifact references
   - SBOM attached

### Permissions

The release workflow requires:
- `contents: write` - Create tags, releases, push changes
- `packages: write` - Push Docker images
- `security-events: write` - Upload security scans
- `id-token: write` - Cosign image signing

## Troubleshooting

### Release didn't trigger after merge

**Check:**
1. Was `version =` line changed in pyproject.toml?
2. Look at workflow run details in Actions tab
3. Check `check-version-changed` job output

### Container image not built

**Check:**
1. Is `build-and-publish-container` job running?
2. Check Docker registry push logs
3. Verify registry credentials are valid

### SBOM upload failed

**Solution:**
- Release.yml uses `gh release upload` with permissions
- If it fails, check `contents: write` permission is set in workflow

## FAQs

**Q: How do I trigger a release?**
A: Update the `version =` line in `pyproject.toml` and merge to main. The release workflow detects the change and runs automatically.

**Q: What if a dev dependency has a critical security fix?**
A: Dev dependency updates don't trigger releases (version detection skips them). The fix will be included in your next production release.

**Q: How do I rollback a release?**
A: Releases are immutable in this setup. Create a new patch release fixing the issue instead.

**Q: Can multiple people work on releases simultaneously?**
A: Yes - each person creates PRs to main. Merge conflicts are handled by git. Only one release workflow runs at a time per merge.

**Q: What's in the SBOM?**
A: All Python dependencies (from pyproject.toml requirements). Useful for compliance, license tracking, and security audits.

**Q: How long does the full release take?**
A: Typically 5-10 minutes:
  - 1 min: Version validation
  - 3-5 min: Container build + scan
  - 1 min: SBOM generation + upload
  - 1 min: GitHub release creation

## See Also

- [CHANGELOG.md](../CHANGELOG.md) - Release history
- [.github/workflows/release.yml](../.github/workflows/release.yml) - Automation source
- [.github/dependabot.yml](../.github/dependabot.yml) - Dependency update config
