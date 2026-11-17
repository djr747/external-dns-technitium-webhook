import pytest

from scripts.pylock_to_requirements import requirements_from_lock


def test_exports_exact_versions_and_environment_markers_in_sorted_order() -> None:
    requirements = requirements_from_lock(
        {
            "packages": [
                {"name": "zulu", "version": "2.1"},
                {"name": "Alpha", "version": "1.2", "marker": "sys_platform == 'linux'"},
            ]
        }
    )

    assert requirements == "Alpha==1.2 ; sys_platform == 'linux'\nzulu==2.1\n"


def test_rejects_invalid_locked_package_names() -> None:
    with pytest.raises(ValueError, match="package names"):
        requirements_from_lock({"packages": [{"name": "bad name", "version": "1.0"}]})


def test_rejects_missing_packages_array() -> None:
    with pytest.raises(ValueError, match="packages array"):
        requirements_from_lock({})
