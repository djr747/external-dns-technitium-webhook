import sys


def test_python_version_is_3_13() -> None:
    """Ensure tests run under Python 3.13 as the project specifies.

    This gives an early, explicit failure if CI or a contributor uses the
    wrong Python runtime. It's intentionally strict: require exactly 3.13.
    """
    major = sys.version_info.major
    minor = sys.version_info.minor
    assert major == 3 and minor == 13, f"Expected Python 3.13, got {major}.{minor}"
