# Security Setup Checklist

## Required Actions

### 1. Configure Snyk (Recommended)

Snyk provides comprehensive security scanning for code, dependencies, and containers.

**Setup:**
1. Sign up at https://snyk.io (free for open source)
2. Navigate to Account Settings → API Token
3. Copy your API token
4. Add to GitHub: Settings → Secrets → Actions
5. Create secret: `SNYK_TOKEN` with your token

**Benefits:**
- AI-powered vulnerability detection
- Dependency vulnerability tracking
- Container security scanning
- Continuous monitoring
- Fix recommendations

### 2. Enable GitHub Security Features

**Dependabot:**
- Settings → Security → Dependabot
- Enable "Dependabot alerts"
- Enable "Dependabot security updates"
- Enable "Dependabot version updates"

**Code Scanning:**
- Settings → Security → Code security and analysis
- Enable "Code scanning"
- Enable "Secret scanning"

**Branch Protection:**
Settings → Branches → Add rule for `main`:
- ✅ Require pull request reviews
- ✅ Require status checks to pass (CI, Security)
- ✅ Require branches to be up to date
- ✅ Require conversation resolution
- ✅ Include administrators

### 3. Verify Workflow Permissions

Settings → Actions → General → Workflow permissions:
- Select "Read and write permissions"
- ✅ Allow GitHub Actions to create and approve pull requests

## Testing the Workflows

### Manual Test Run
1. Go to Actions tab
2. Select "CI" workflow
3. Click "Run workflow"
4. Select branch: `main`
5. Click "Run workflow"

### Verify Security Scanning
1. Make a test commit
2. Wait for workflows to complete
3. Check Security tab → Code scanning alerts
4. Should see results from:
   - CodeQL
   - Trivy
   - Snyk (if configured)
   - Bandit
   - Semgrep

### Test Scheduled Rebuild
1. Go to Actions → Scheduled Security Rebuild
2. Click "Run workflow"
3. Verify it builds with `no-cache: true`
4. Check for vulnerability report in summary

## Monitoring

### Weekly Checks
- Review Security tab for new alerts
- Check scheduled rebuild results
- Review Dependabot PRs
- Monitor Snyk dashboard (if configured)

### Release Process
1. Ensure all tests pass
2. Review security scan results
3. Update version in commit message
4. Tag release: `git tag v1.0.0`
5. Push tag: `git push origin v1.0.0`
6. Verify release workflow completes
7. Check GitHub releases page
8. Verify container images in GHCR (ghcr.io)

## Troubleshooting

### Workflow Fails with "Secret not found"
- Verify secret name matches exactly (case-sensitive)
- Check secret is added at repository level (not organization)
- Ensure workflow has permission to access secrets

### Snyk Scans Skipped
- Workflow continues even if `SNYK_TOKEN` missing
- Add secret to enable Snyk scans
- Or remove Snyk steps from workflows

### Container Build Fails
- Check Docker Hub rate limits
- Verify base image (UBI10) is accessible
- Review build logs in Actions tab

### Security Alerts Not Appearing
- Ensure SARIF upload steps completed successfully
- Check Security tab → Settings → Code scanning
- Verify CodeQL is enabled
- Allow 5-10 minutes for processing

## Best Practices

### Commit Messages
Use conventional commits for automatic changelog:
```
feat: add new DNS record type support
fix: resolve timeout issue in webhook handler
sec: update dependencies for CVE-2024-1234
docs: update deployment guide
chore: update development dependencies
```

### Security Response
When vulnerabilities are detected:
1. Review severity and impact
2. Check for available patches
3. Update dependencies if possible
4. If no patch available, assess risk
5. Document decision in security advisory
6. Monitor for updates

### Regular Maintenance
- Review and merge Dependabot PRs weekly
- Check scheduled rebuild results
- Update workflows quarterly
- Review and rotate secrets annually
- Keep documentation updated

## Support and Resources

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Snyk Documentation](https://docs.snyk.io)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [SBOM Guide](https://www.cisa.gov/sbom)
- [SLSA Framework](https://slsa.dev)
