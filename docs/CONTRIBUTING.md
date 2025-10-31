# Contributing to external-dns-technitium-webhook

Thank you for your interest in contributing to this project! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions related to this project.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/djr747/external-dns-technitium-webhook/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS, Python version, etc.)
   - Relevant logs or screenshots

### Suggesting Features

1. Check existing issues and discussions
2. Create a new issue describing:
   - The problem you're trying to solve
   - Your proposed solution
   - Any alternatives you've considered

### Pull Requests

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting:
   ```bash
   make test
   make lint
   make type-check
   ```
5. Commit your changes with clear messages
6. Push to your fork
7. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/external-dns-technitium-webhook.git
cd external-dns-technitium-webhook

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
make install-dev

# Run tests
make test
```

## Code Style

This project uses:
- **Ruff** for linting and formatting
- **mypy** for type checking
- **Bandit** for security scanning

Run formatting and checks:
```bash
make format      # Format code
make lint        # Check linting
make type-check  # Type checking
make security    # Security scanning
```

## Testing

- Write tests for new features
- Maintain or improve code coverage
- Run the full test suite before submitting PRs

```bash
make test        # Run tests
make test-cov    # Run with coverage report
```

## Commit Messages

Use clear, descriptive commit messages:
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and PRs where appropriate

Examples:
```
Add support for SRV records

Fix issue with token renewal (#123)

Update dependencies to fix CVE-2024-12345
```

## Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions/classes
- Update type hints
- Include examples where helpful

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
