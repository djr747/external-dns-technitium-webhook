from typing import Any

import pytest

from scripts.snyk_to_copa import convert_report


def _expected_update(finding: dict[str, Any]) -> dict[str, str]:
    return {
        "name": finding["packageName"],
        "installedVersion": finding["version"],
        "fixedVersion": finding["fixedIn"][0],
        "vulnerabilityID": finding["id"],
    }


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
    expected_updates = [
        _expected_update(finding)
        for finding in report["vulnerabilities"]
        if finding["packageManager"] == "deb" and finding["fixedIn"]
    ]
    assert manifest["updates"] == expected_updates


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

    assert manifest["updates"] == [_expected_update(report["vulnerabilities"][0])]


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

    assert manifest["updates"] == [
        _expected_update(finding) for finding in report["vulnerabilities"]
    ]


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

    assert manifest["updates"] == [_expected_update(report["vulnerabilities"][0])]


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
