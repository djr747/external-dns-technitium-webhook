# Security Policy

Thank you for taking the time to review the security posture of this project.

We take security seriously. This document explains how to report vulnerabilities
and how we maintain secure base images and dependencies.

## Supported versions

We run continuous security scanning (CodeQL, Trivy, Snyk, Grype) in CI and aim
to keep the container base image minimal and up-to-date. The project uses a
Chainguard Python base image for runtime to reduce OS-level CVEs.

## Reporting a Vulnerability

Please report security issues privately by opening a GitHub Security Advisory.
Go to: https://github.com/djr747/external-dns-technitium-webhook/security/advisories/new

**Important:** If you open a public issue, sensitive details may be exposed.

When reporting, include:
- A brief summary
- Affected version or commit
- Steps to reproduce (if applicable)
- Expected vs actual behavior
- Any PoC code or exploit details (send privately)

We will acknowledge receipt within 48 hours and aim to provide a remediation
timeline or a mitigated release within 7 calendar days for critical issues. We
may extend this timeline for complex issues but will communicate status via
the advisory.

## Base image & dependency updates

We use the Chainguard minimal Python base image. Dependabot is configured to
monitor Dockerfile base-image updates and will open PRs for image updates. We
also run daily dependency scans and will triage new findings in priority order.

## Security tools we run

- CodeQL (code-scanning)
- Trivy / Grype (container image scanning)
- Snyk (dependency scanning)
- bandit / semgrep (additional static analysis)

## Disclosure and coordination

If you need coordinated disclosure, please use GitHub Security Advisories:
https://github.com/djr747/external-dns-technitium-webhook/security/advisories

We will work with reporters to coordinate a fix and public notification.

Thank you — maintainers.
