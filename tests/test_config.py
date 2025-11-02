"""Unit tests for configuration module."""

import pytest
from pydantic import ValidationError

from external_dns_technitium_webhook.config import Config


def test_config_defaults() -> None:
    """Test default configuration values."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
    )

    assert config.listen_address == "0.0.0.0"
    assert config.listen_port == 8888
    assert config.health_port == 8080
    assert config.log_level == "INFO"
    assert config.domain_filters is None


def test_config_required_fields() -> None:
    """Test that required fields must be provided."""
    with pytest.raises(ValidationError):
        Config()


def test_domain_filter_list() -> None:
    """Test domain filter parsing."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
        domain_filters="foo.example.com;bar.example.com",
    )

    assert config.domain_filter_list == ["foo.example.com", "bar.example.com"]


def test_domain_filter_list_empty() -> None:
    """Test empty domain filter."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
    )

    assert config.domain_filter_list == []


def test_technitium_endpoints_normalization() -> None:
    """Technitium endpoints should be normalized and deduplicated."""
    config = Config(
        technitium_url="  http://primary:5380/  ",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
        technitium_failover_urls=" http://primary:5380/ ; http://secondary:5380/// ",
    )

    assert config.technitium_endpoints == [
        "http://primary:5380",
        "http://secondary:5380",
    ]


def test_technitium_endpoints_skip_blank_entries() -> None:
    """Whitespace-only failover entries should be ignored."""
    config = Config(
        technitium_url="http://primary.example.com",
        technitium_failover_urls=";   ; https://backup.example.com ",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )

    endpoints = config.technitium_endpoints

    assert endpoints == [
        "http://primary.example.com",
        "https://backup.example.com",
    ]


def test_technitium_endpoints_ignore_blank_primary() -> None:
    """Blank primary URL should be skipped when computing endpoints."""
    config = Config(
        technitium_url="   ",
        technitium_failover_urls="https://backup.example.com",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )

    endpoints = config.technitium_endpoints

    assert endpoints == [
        "https://backup.example.com",
    ]


def test_bind_address() -> None:
    """Test bind address property."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
        listen_address="127.0.0.1",
        listen_port=8080,
    )

    assert config.bind_address == "127.0.0.1:8080"


def test_password_redaction_in_repr() -> None:
    """Test that password is redacted in __repr__."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="supersecret",
        zone="example.com",
    )

    repr_str = repr(config)
    assert "supersecret" not in repr_str
    assert "***REDACTED***" in repr_str


def test_password_redaction_in_model_dump() -> None:
    """Test that password is redacted in model_dump()."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="supersecret",
        zone="example.com",
    )

    dumped = config.model_dump()
    assert dumped["technitium_password"] == "***REDACTED***"
    assert "supersecret" not in str(dumped)


def test_ca_bundle_validation_missing_file() -> None:
    """Test that config validation fails when CA bundle file does not exist."""
    import pytest

    # Use a non-existent path
    nonexistent_ca = "/nonexistent/path/to/ca.pem"
    with pytest.raises(ValueError, match="does not exist"):
        Config(
            technitium_url="http://localhost:5380",
            technitium_username="admin",
            technitium_password="admin",
            zone="example.com",
            technitium_verify_ssl=True,
            technitium_ca_bundle_file=nonexistent_ca,
        )


def test_ca_bundle_validation_with_valid_file() -> None:
    """Test that config validation succeeds when CA bundle file exists."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        ca_file = f"{tmpdir}/ca.pem"
        # Create a valid self-signed CA certificate for testing
        import subprocess

        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-x509",
                "-days",
                "1",
                "-nodes",
                "-out",
                ca_file,
                "-keyout",
                f"{tmpdir}/ca.key",
                "-subj",
                "/CN=test-ca",
            ],
            check=True,
            capture_output=True,
        )

        config = Config(
            technitium_url="http://localhost:5380",
            technitium_username="admin",
            technitium_password="admin",
            zone="example.com",
            technitium_verify_ssl=True,
            technitium_ca_bundle_file=ca_file,
        )
        assert config.technitium_ca_bundle_file == ca_file


def test_ca_bundle_not_required_when_verify_ssl_false() -> None:
    """Test that CA bundle is optional when verify_ssl is False."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
        technitium_verify_ssl=False,
        technitium_ca_bundle_file="/nonexistent/path.pem",
    )
    # Should not raise even though the file does not exist
    assert config.technitium_verify_ssl is False
    assert config.technitium_ca_bundle_file == "/nonexistent/path.pem"


def test_ca_bundle_validation_unreadable_file() -> None:
    """Test that config validation fails when CA bundle file is not readable."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        ca_file = f"{tmpdir}/ca.pem"
        with open(ca_file, "w") as f:
            f.write("test")
        # Make the file unreadable
        os.chmod(ca_file, 0o000)
        try:
            with pytest.raises(ValueError) as exc_info:
                Config(
                    technitium_url="http://localhost:5380",
                    technitium_username="admin",
                    technitium_password="admin",
                    zone="example.com",
                    technitium_verify_ssl=True,
                    technitium_ca_bundle_file=ca_file,
                )
            assert "not readable" in str(exc_info.value).lower()
        finally:
            # Restore permissions for cleanup
            os.chmod(ca_file, 0o600)
