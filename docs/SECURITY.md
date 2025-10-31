# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please follow these steps:

1. **Do NOT** open a public issue
2. Email security details to: your.email@example.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

We will respond within 48 hours and provide:
- Acknowledgment of your report
- Timeline for investigation and fix
- Credit for the discovery (if desired)

## Security Measures

This project implements several security measures:

### Code Security
- **Bandit**: Static analysis for finding common security issues.
- **CodeQL**: Advanced code analysis

### Container Security
- **Trivy**: Container image vulnerability scanning
- Multi-stage Docker builds to minimize attack surface
- Non-root user in container
- Minimal base image (python:3.11-slim)

### Dependencies
- Regular dependency updates via Dependabot
- Automated security scanning in CI/CD
- Pinned dependency versions

### Best Practices
- Secrets management via environment variables
- HTTPS for all external communications
- Input validation and sanitization
- Principle of least privilege

## Known Security Considerations

### Authentication
- Technitium credentials are passed via environment variables
- Token-based authentication with automatic renewal
- Tokens are stored in memory only (not persisted to disk)

### Network Security
- All API communication over HTTP(S)
- No direct database access
- Minimal attack surface

### Static analysis compatibility (Bandit)

Note: Bandit is used for static analysis in CI to detect common security issues. There is a known compatibility issue where recent Bandit runs may raise AST parsing exceptions when executed under CPython 3.14 in some environments. Because our CI/build environment is (and should be) Python 3.12, security scans in CI run Bandit under Python 3.12 to avoid this issue.

If you run security checks locally and see AST-related errors from Bandit, run Bandit under a Python 3.12 virtual environment. Example:

```bash
# create a reproducible py3.12 venv (if you have python3.12 installed)
python3.12 -m venv .venv312
. .venv312/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
# run Bandit against the package under Python 3.12
python -m bandit -r external_dns_technitium_webhook
```

What we do in CI
- Bandit scans are executed under Python 3.12 in CI to ensure stable AST parsing and consistent results.
- We recommend running the same environment locally when reproducing CI security scans.

False positives
- Bandit may flag intentional patterns (for example, code that redacts secrets before logging). We review such findings and, when appropriate, add a `# nosec` comment with an explanation so CI noise is reduced while preserving security intent.

## Security Updates

Security updates are released as soon as possible after a vulnerability is confirmed. Users are encouraged to:

1. Enable GitHub security alerts
2. Subscribe to release notifications
3. Keep dependencies up to date
4. Review security scan results in CI/CD

## Responsible Disclosure

We practice responsible disclosure and will:
- Investigate all legitimate reports
- Work to fix vulnerabilities quickly
- Credit researchers (if desired)
- Notify users of security updates

Thank you for helping keep this project secure!
