from typing import Any

import pytest

from scripts.snyk_to_copa import convert_report, is_debian_package_manager


def _expected_updates_from_report(report: dict[str, Any]) -> list[dict[str, str]]:
    updates: dict[tuple[str, str, str], dict[str, str]] = {}
    for finding in report["vulnerabilities"]:
        package_manager = str(finding.get("packageManager", "")).lower()
        if package_manager not in {
            "apt",
            "deb",
            "debian",
            "dpkg",
        } and not package_manager.startswith("debian:"):
            continue

        fixed_in = finding.get("fixedIn", [])
        if isinstance(fixed_in, str):
            fixed_versions = [fixed_in]
        elif isinstance(fixed_in, list):
            fixed_versions = fixed_in
        else:
            continue
        if not fixed_versions or not isinstance(fixed_versions[0], str):
            continue

        name = str(finding.get("packageName") or finding.get("pkgName") or "")
        installed = str(finding.get("version") or finding.get("pkgVersion") or "")
        fixed_version = fixed_versions[0]
        key = (name, installed, fixed_version)
        updates.setdefault(
            key,
            {
                "name": name,
                "installedVersion": installed,
                "fixedVersion": fixed_version,
                "vulnerabilityID": str(finding.get("id") or finding.get("issueId") or ""),
            },
        )

    return sorted(
        updates.values(),
        key=lambda update: (
            update["name"],
            update["installedVersion"],
            update["fixedVersion"],
            update["vulnerabilityID"],
        ),
    )


def test_converts_fixable_debian_packages_and_ignores_app_dependencies() -> None:
    report = {
        "vulnerabilities": [
            {
                "id": "SNYK-DEBIAN13-ZLIB-123",
                "packageManager": "deb",
                "packageName": "zlib1g",
                "version": "1.3.dfsg+really1.3.1-1",
                "fixedIn": ["1.3.dfsg+really1.3.1-2"],
            },
            {
                "id": "SNYK-PYTHON-FASTAPI-456",
                "packageManager": "pip",
                "packageName": "fastapi",
                "version": "0.140.0",
                "fixedIn": ["0.141.0"],
            },
            {
                "id": "SNYK-DEBIAN13-OPENSSL-789",
                "packageManager": "deb",
                "packageName": "openssl",
                "version": "3.0.0-1",
                "fixedIn": [],
            },
        ]
    }
    manifest = convert_report(report, architecture="arm64", os_version="13")

    assert manifest["apiVersion"] == "v1alpha1"
    assert manifest["metadata"] == {
        "os": {"type": "debian", "version": "13"},
        "config": {"arch": "arm64"},
    }
    assert manifest["updates"] == _expected_updates_from_report(report)


def test_deduplicates_findings_for_the_same_package_when_the_fix_agrees() -> None:
    report = {
        "vulnerabilities": [
            {
                "id": "CVE-1",
                "packageManager": "deb",
                "packageName": "zlib1g",
                "version": "1.3-1",
                "fixedIn": ["1.3-2"],
            },
            {
                "id": "CVE-2",
                "packageManager": "deb",
                "packageName": "zlib1g",
                "version": "1.3-1",
                "fixedIn": ["1.3-2"],
            },
        ]
    }
    manifest = convert_report(report, architecture="amd64", os_version="13")

    assert manifest["updates"] == _expected_updates_from_report(report)


def test_preserves_successive_cve_fixes_for_the_same_installed_package() -> None:
    report = {
        "vulnerabilities": [
            {
                "id": "CVE-1",
                "packageManager": "deb",
                "packageName": "zlib1g",
                "version": "1.3-1",
                "fixedIn": ["1.3-2"],
            },
            {
                "id": "CVE-2",
                "packageManager": "deb",
                "packageName": "zlib1g",
                "version": "1.3-1",
                "fixedIn": ["1.3-3"],
            },
        ]
    }

    manifest = convert_report(report, architecture="amd64", os_version="13")

    assert manifest["updates"] == _expected_updates_from_report(report)


def test_rejects_missing_snyk_vulnerability_list() -> None:
    with pytest.raises(ValueError, match="vulnerabilities array"):
        convert_report({}, architecture="amd64", os_version="13")


def test_converts_distro_qualified_debian_package_managers() -> None:
    report = {
        "vulnerabilities": [
            {
                "id": "SNYK-DEBIAN13-ZLIB-123",
                "packageManager": "debian:13",
                "packageName": "zlib1g",
                "version": "1.3-1",
                "fixedIn": ["1.3-2"],
            }
        ]
    }
    manifest = convert_report(report, architecture="amd64", os_version="13")

    assert manifest["updates"] == _expected_updates_from_report(report)


def test_rejects_spaces_in_distro_qualified_package_manager() -> None:
    assert is_debian_package_manager("debian:13.1")
    assert not is_debian_package_manager("debian:13 beta")


def test_ignores_non_debian_distro_qualified_package_managers() -> None:
    manifest = convert_report(
        {
            "vulnerabilities": [
                {
                    "id": "SNYK-UBUNTU-ZLIB-123",
                    "packageManager": "ubuntu:22.04",
                    "packageName": "zlib1g",
                    "version": "1.3-1",
                    "fixedIn": ["1.3-2"],
                }
            ]
        },
        architecture="amd64",
        os_version="13",
    )

    assert manifest["updates"] == []
