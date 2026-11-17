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


def test_concrete_pep440_release_suffixes_are_accepted_but_wildcards_are_not() -> None:
    requirements = requirements_from_lock(
        {
            "packages": [
                {"name": "release-candidates", "version": "1!2.0rc1"},
                {"name": "post-releases", "version": "2.0.post1"},
                {"name": "development", "version": "2.0.dev3+vendor.1"},
            ]
        }
    )

    assert "1!2.0rc1" in requirements
    assert "2.0.post1" in requirements
    assert "2.0.dev3+vendor.1" in requirements
    with pytest.raises(ValueError, match="invalid locked version"):
        requirements_from_lock({"packages": [{"name": "example", "version": "*"}]})


def test_rejects_missing_packages_array() -> None:
    with pytest.raises(ValueError, match="packages array"):
        requirements_from_lock({})
