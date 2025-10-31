# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial Python implementation of ExternalDNS Technitium webhook
- Support for A, AAAA, CNAME, and TXT records
- Automatic zone creation
- Domain filtering support
- Automatic token renewal
- Comprehensive test suite
- Docker support with multi-stage builds
- GitHub Actions CI/CD pipeline
- Security scanning with Trivy and Bandit
- Code quality checks with Ruff and mypy
- Multi-platform Docker builds (linux/amd64, linux/arm64)
- Health check endpoint
- Kubernetes deployment example
- GitHub issue templates (bug report, feature request, question)
- Pull request template with comprehensive checklist
- Dependabot configuration for automated dependency updates
- Dependency health check script (`scripts/check_dependencies.py`)
- Monitoring and observability documentation (`docs/MONITORING.md`)
- Performance and reliability guide (`docs/PERFORMANCE.md`)
- `make check-deps` command for dependency management

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- N/A

## [0.1.0] - 2025-01-XX

### Added
- Initial release
- Basic ExternalDNS webhook functionality
- Technitium DNS integration

[Unreleased]: https://github.com/djr747/external-dns-technitium-webhook/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/djr747/external-dns-technitium-webhook/releases/tag/v0.1.0
