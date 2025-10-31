#!/usr/bin/env python3
"""Setup script for development environment."""

from __future__ import annotations

import subprocess
import sys


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and print the result."""
    print(f"\n{'=' * 60}")
    print(f"{description}...")
    print(f"{'=' * 60}")
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        return False


def main() -> int:
    """Setup development environment."""
    print("\n🚀 Setting up development environment for external-dns-technitium-webhook\n")

    # Check Python version

    # Install dependencies
    if not run_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        "Upgrading pip",
    ):
        return 1

    if not run_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        "Installing dependencies",
    ):
        return 1

    # Run initial checks
    print("\n📋 Running initial code quality checks...\n")

    checks = [
        (["ruff", "format", "."], "Code formatting"),
        (["ruff", "check", "."], "Linting"),
        (["mypy", "external_dns_technitium_webhook"], "Type checking"),
        (["pytest", "--version"], "Test framework"),
    ]

    all_passed = True
    for cmd, description in checks:
        if not run_command(cmd, description):
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ Development environment setup complete!")
        print("\nNext steps:")
        print("  1. Copy .env.example to .env and configure")
        print("  2. Run tests: make test")
        print("  3. Start development: python -m external_dns_technitium_webhook.main")
    else:
        print("⚠️  Setup completed with some warnings")
        print("Some checks failed, but you can still proceed")

    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
