import pytest

from scripts.snyk_to_copa import convert_report


def test_converts_fixable_debian_packages_and_ignores_app_dependencies() -> None:
    manifest = convert_report(
        {
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
        },
        architecture="arm64",
        os_version="13",
    )

    assert manifest == {
        "apiVersion": "v1alpha1",
        "metadata": {
            "os": {"type": "debian", "version": "13"},
            "config": {"arch": "arm64"},
        },
        "updates": [
            {
                "name": "zlib1g",
                "installedVersion": "1.3.dfsg+really1.3.1-1",
                "fixedVersion": "1.3.dfsg+really1.3.1-2",
                "vulnerabilityID": "SNYK-DEBIAN13-ZLIB-123",
            }
        ],
    }


def test_deduplicates_findings_for_the_same_package_when_the_fix_agrees() -> None:
    manifest = convert_report(
        {
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
        },
        architecture="amd64",
        os_version="13",
    )

    assert manifest["updates"][0]["vulnerabilityID"] == "CVE-1"


def test_rejects_conflicting_fixes_for_the_same_installed_package() -> None:
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

    with pytest.raises(ValueError, match="conflicting fixed versions"):
        convert_report(report, architecture="amd64", os_version="13")


def test_rejects_missing_snyk_vulnerability_list() -> None:
    with pytest.raises(ValueError, match="vulnerabilities array"):
        convert_report({}, architecture="amd64", os_version="13")
