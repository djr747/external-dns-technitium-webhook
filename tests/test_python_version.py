import sys


def test_python_version_is_supported() -> None:
    """Ensure tests run under a supported Python runtime (3.13 or 3.14).

    This keeps a clear early failure if CI or a contributor uses an
    unsupported Python runtime while allowing local development on 3.14.
    """
    major = sys.version_info.major
    minor = sys.version_info.minor
    supported = major == 3 and minor in (13, 14)
    assert supported, f"Expected Python 3.13 or 3.14, got {major}.{minor}"
