# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please follow these steps:

1. **Do NOT** open a public issue
2. Email security details to: <your.email@example.com>
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
- **Chainguard Python**: Ultra-minimal base image with zero CVEs, daily security updates, SLSA Level 3 provenance
- Multi-stage Docker builds to minimize attack surface
- Non-root user in container
- Distroless runtime image (no shell, package managers, or unnecessary tools)

### Dependencies

- Regular dependency updates via Dependabot
- Automated security scanning in CI/CD
- Pinned dependency versions

### TLS/SSL Security

- **Strong cipher enforcement**: All TLS connections use OpenSSL SECLEVEL=2, requiring:
  - RSA keys: 2048 bits or larger
  - Modern, strong cipher suites
  - TLS 1.2 or higher
- Certificate verification can be disabled for development (`TECHNITIUM_VERIFY_SSL=false`), but cipher strength remains enforced
- Support for custom CA certificates via `TECHNITIUM_CA_BUNDLE_FILE`

### GitHub Actions Security

- **Least-privilege permissions**: Each workflow job declares only required permissions (not inherited at workflow level)
- Permissions scoped per job:
  - CI jobs: `contents: read` only (read-only source access)
  - Security scanning jobs: `contents: read` + `security-events: write` (scan reporting)
  - Container publishing jobs: `packages: write` + `id-token: write` (registry push and image signing)
- Read-only workflows cannot inadvertently modify code or introduce supply chain risks

### Best Practices

- Secrets management via environment variables (passwords automatically redacted)
- HTTPS for all external communications (enforced strong ciphers)
- Input validation and sanitization
- Principle of least privilege (pod security, GitHub Actions permissions, RBAC)

## Known Security Considerations

### Authentication

- Technitium credentials are passed via environment variables (never logged)
- Token-based authentication with automatic renewal
- Tokens are stored in memory only (not persisted to disk)
- Passwords redacted from all logging and error messages

### Cryptography

- All TLS connections enforce strong ciphers (SECLEVEL=2: 2048-bit+ RSA, strong suites, TLS 1.2+)
- Independent from certificate verification toggle
- Protects against downgrade attacks and weak cipher negotiation

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
