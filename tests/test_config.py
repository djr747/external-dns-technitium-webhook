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
    assert config.listen_port == 3000
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
