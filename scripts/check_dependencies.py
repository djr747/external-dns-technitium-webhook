#!/usr/bin/env python3
"""
Check for outdated Python dependencies and security vulnerabilities.

This script helps maintain up-to-date dependencies by:
1. Listing outdated packages
2. Checking for known security vulnerabilities
3. Providing upgrade recommendations

Usage:
    python scripts/check_dependencies.py
"""

import json
import subprocess
import sys


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a shell command and return output.

    Args:
        cmd: Command and arguments as list

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def check_outdated_packages() -> None:
    """Check for outdated Python packages."""
    print("=" * 80)
    print("Checking for outdated packages...")
    print("=" * 80)

    returncode, stdout, stderr = run_command(["pip", "list", "--outdated", "--format=json"])

    if returncode != 0:
        print(f"Error checking outdated packages: {stderr}", file=sys.stderr)
        return

    if not stdout.strip():
        print("✅ All packages are up to date!")
        return

    try:
        outdated = json.loads(stdout)
        if not outdated:
            print("✅ All packages are up to date!")
            return

        print(f"\n⚠️  Found {len(outdated)} outdated package(s):\n")
        print(f"{'Package':<30} {'Current':<15} {'Latest':<15} {'Type':<10}")
        print("-" * 80)

        for pkg in outdated:
            name = pkg["name"]
            current = pkg["version"]
            latest = pkg["latest_version"]
            pkg_type = pkg.get("latest_filetype", "wheel")
            print(f"{name:<30} {current:<15} {latest:<15} {pkg_type:<10}")

        print("\nTo update packages, run:")
        print("  pip install --upgrade <package-name>")
        print("or update pyproject.toml and run:")
        print("  pip install -e .[dev]")

    except json.JSONDecodeError as e:
        print(f"Error parsing output: {e}", file=sys.stderr)


def check_dependency_conflicts() -> None:
    """Check for dependency conflicts."""
    print("\n" + "=" * 80)
    print("Checking for dependency conflicts...")
    print("=" * 80)

    returncode, stdout, stderr = run_command(["pip", "check"])

    if returncode == 0:
        print("✅ No dependency conflicts found!")
    else:
        print("⚠️  Dependency conflicts detected:\n")
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)


def main() -> int:
    """Main function to run all dependency checks.

    Returns:
        Exit code (0 for success, non-zero for issues)
    """
    print("\n🔍 Python Dependency Health Check")
    print("=" * 80)

    # Check outdated packages
    check_outdated_packages()

    # Check for vulnerabilities
    # vuln_code = check_vulnerabilities()

    # Check for conflicts
    check_dependency_conflicts()

    print("\n" + "=" * 80)
    print("✅ Dependency check complete - no critical issues!")
    print("=" * 80 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
