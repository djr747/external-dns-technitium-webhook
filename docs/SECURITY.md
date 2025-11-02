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
- **Semgrep**: Pattern-based security vulnerability detection
- **CodeQL**: Advanced semantic code analysis

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

### Static analysis (Semgrep)

Semgrep is used for pattern-based security scanning in CI to detect common vulnerabilities and security issues. Run it locally with:

```bash
make security  # or
semgrep --config=auto external_dns_technitium_webhook/
```

Security rules are automatically updated from Semgrep's public rule registry. This provides comprehensive coverage for Python security patterns without compatibility issues.

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
