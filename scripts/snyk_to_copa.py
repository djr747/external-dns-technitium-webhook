#!/usr/bin/env python3
"""Convert Snyk container JSON into Copa's native OS package update manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEBIAN_PACKAGE_MANAGERS = {"apt", "deb", "debian", "dpkg"}


def convert_report(report: dict[str, Any], *, architecture: str, os_version: str) -> dict[str, Any]:
    """Map unambiguous, fixable Debian OS findings to Copa v1alpha1."""
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise ValueError("Snyk report must contain a vulnerabilities array")

    updates: dict[tuple[str, str], dict[str, str]] = {}
    for item in vulnerabilities:
        if not isinstance(item, dict):
            raise ValueError("Snyk vulnerability entries must be objects")

        package_manager = item.get("packageManager", "")
        if not isinstance(package_manager, str):
            raise ValueError("packageManager must be a string when present")
        if package_manager.lower() not in DEBIAN_PACKAGE_MANAGERS:
            continue

        name = item.get("packageName") or item.get("pkgName")
        installed = item.get("version") or item.get("pkgVersion")
        vulnerability_id = item.get("id") or item.get("issueId")
        fixed_in = item.get("fixedIn", [])
        if isinstance(fixed_in, str):
            fixed_in = [fixed_in]
        if not isinstance(fixed_in, list):
            raise ValueError("fixedIn must be a string or array")
        fixed_versions = [value for value in fixed_in if isinstance(value, str) and value]

        # Findings with no published package fix are left for the final Snyk gate.
        if not fixed_versions:
            continue
        if not all(
            isinstance(value, str) and value for value in (name, installed, vulnerability_id)
        ):
            raise ValueError("fixable Debian findings need package, installed version, and ID")

        key = (name, installed)
        update = {
            "name": name,
            "installedVersion": installed,
            "fixedVersion": fixed_versions[0],
            "vulnerabilityID": vulnerability_id,
        }
        previous = updates.get(key)
        if previous and previous["fixedVersion"] != update["fixedVersion"]:
            raise ValueError(
                f"conflicting fixed versions for {name} {installed}; refusing ambiguous patch"
            )
        if not previous:
            updates[key] = update

    return {
        "apiVersion": "v1alpha1",
        "metadata": {
            "os": {"type": "debian", "version": os_version},
            "config": {"arch": architecture},
        },
        "updates": sorted(updates.values(), key=lambda item: item["name"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Snyk container JSON report")
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--os-version", default="13")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Snyk report root must be an object")
    manifest = convert_report(report, architecture=args.arch, os_version=args.os_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{args.arch}: {len(manifest['updates'])} fixable Debian OS package(s)")


if __name__ == "__main__":
    main()
