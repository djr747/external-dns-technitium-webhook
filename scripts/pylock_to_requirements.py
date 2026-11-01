#!/usr/bin/env python3
"""Export locked PEP 751 packages to a pip requirements file for Snyk."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path
from typing import Any

PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PACKAGE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+!_-]*$")


def requirements_from_lock(lock: dict[str, Any]) -> str:
    """Render every locked package as an exact pin, preserving environment markers."""
    packages = lock.get("packages")
    if not isinstance(packages, list):
        raise ValueError("pylock.toml must contain a packages array")

    requirements: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("pylock.toml package entries must be tables")
        name = package.get("name")
        version = package.get("version")
        marker = package.get("marker")
        if not isinstance(name, str) or not PACKAGE_NAME.fullmatch(name):
            raise ValueError("pylock.toml package names must be valid distribution names")
        if not isinstance(version, str) or not PACKAGE_VERSION.fullmatch(version):
            raise ValueError(f"invalid locked version for {name}")

        requirement = f"{name}=={version}"
        if marker is not None:
            if not isinstance(marker, str) or "\n" in marker or "\r" in marker:
                raise ValueError(f"invalid environment marker for {name}")
            requirement += f" ; {marker}"
        requirements.append(requirement)

    return "\n".join(sorted(requirements, key=str.casefold)) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path, help="PEP 751 pylock.toml file")
    parser.add_argument("output", type=Path, help="pip requirements output path")
    args = parser.parse_args()

    lock = tomllib.loads(args.lock.read_text(encoding="utf-8"))
    args.output.write_text(requirements_from_lock(lock), encoding="utf-8")


if __name__ == "__main__":
    main()
