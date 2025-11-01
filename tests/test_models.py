"""Unit tests for data models."""

import pytest
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.models import (
    Changes,
    DomainFilter,
    Endpoint,
    ProviderSpecificProperty,
)


def test_endpoint_serialization() -> None:
    """Test endpoint serialization to dict."""
    endpoint = Endpoint(
        dnsName="example.com",
        targets=["1.2.3.4"],
        recordType="A",
        recordTTL=300,
        setIdentifier="",
    )

    data = endpoint.model_dump(by_alias=True)
    assert data["dnsName"] == "example.com"
    assert data["targets"] == ["1.2.3.4"]
    assert data["recordType"] == "A"
    assert data["recordTTL"] == 300


def test_endpoint_deserialization() -> None:
    """Test endpoint deserialization from dict."""
    data = {
        "dnsName": "example.com",
        "targets": ["1.2.3.4"],
        "recordType": "A",
        "recordTTL": 300,
    }

    endpoint = Endpoint.model_validate(data)
    assert endpoint.dns_name == "example.com"
    assert endpoint.targets == ["1.2.3.4"]
    assert endpoint.record_type == "A"
    assert endpoint.record_ttl == 300


def test_changes_deserialization() -> None:
    """Test changes deserialization."""
    data = {
        "create": [
            {
                "dnsName": "create.example.com",
                "targets": ["1.1.1.1"],
                "recordType": "A",
            }
        ],
        "updateOld": [
            {
                "dnsName": "update.example.com",
                "targets": ["2.2.2.2"],
                "recordType": "A",
            }
        ],
        "updateNew": [
            {
                "dnsName": "update.example.com",
                "targets": ["3.3.3.3"],
                "recordType": "A",
            }
        ],
        "delete": [
            {
                "dnsName": "delete.example.com",
                "targets": ["4.4.4.4"],
                "recordType": "A",
            }
        ],
    }

    changes = Changes.model_validate(data)
    assert changes.create is not None
    assert len(changes.create) == 1
    assert changes.create[0].dns_name == "create.example.com"

    assert changes.update_old is not None
    assert len(changes.update_old) == 1

    assert changes.update_new is not None
    assert len(changes.update_new) == 1

    assert changes.delete is not None
    assert len(changes.delete) == 1


def test_domain_filter() -> None:
    """Test domain filter model."""
    filter = DomainFilter(
        filters=["example.com", "test.com"],
        exclude=["skip.example.com"],
    )

    assert filter.filters == ["example.com", "test.com"]
    assert filter.exclude == ["skip.example.com"]


def test_provider_specific_property() -> None:
    """Test provider specific property."""
    prop = ProviderSpecificProperty(name="custom", value="value")
    assert prop.name == "custom"
    assert prop.value == "value"


def test_endpoint_validation_rejects_empty_dns_name() -> None:
    """Endpoint DNS name validator should reject empty strings."""
    with pytest.raises(ValueError, match="DNS name cannot be empty"):
        Endpoint.model_validate(
            {
                "dnsName": "",
                "targets": ["1.2.3.4"],
                "recordType": "A",
                "setIdentifier": "",
            }
        )


def test_endpoint_validation_rejects_long_label(mocker: MockerFixture) -> None:
    """Endpoint DNS name validator rejects labels longer than 63 characters."""
    long_label = "a" * 64
    dns_name = f"{long_label}.example.com"
    mocker.patch("external_dns_technitium_webhook.models.re.match", return_value=True)
    with pytest.raises(ValueError, match="DNS label too long"):
        Endpoint.model_validate(
            {
                "dnsName": dns_name,
                "targets": ["1.2.3.4"],
                "recordType": "A",
                "setIdentifier": "",
            }
        )


def test_endpoint_ttl_logs_warning_for_high_value(caplog: pytest.LogCaptureFixture) -> None:
    """TTL validator should issue a warning for unusually large TTL values."""
    caplog.set_level("WARNING")
    endpoint = Endpoint(
        dnsName="example.com",
        targets=["1.2.3.4"],
        recordType="A",
        recordTTL=100000,
        setIdentifier="",
    )

    assert endpoint.record_ttl == 100000
    assert "Unusually high TTL value" in caplog.text


def test_endpoint_validation_rejects_excessive_length() -> None:
    """Endpoint DNS name validator rejects names longer than 253 characters."""
    long_name = "a" * 254
    with pytest.raises(ValueError, match="DNS name too long"):
        Endpoint.model_validate(
            {
                "dnsName": f"{long_name}.com",
                "targets": ["1.2.3.4"],
                "recordType": "A",
                "setIdentifier": "",
            }
        )


def test_endpoint_validation_rejects_invalid_format() -> None:
    """Endpoint DNS name validator rejects names with invalid characters."""
    with pytest.raises(ValueError, match="Invalid DNS name format"):
        Endpoint.model_validate(
            {
                "dnsName": "invalid_name!",
                "targets": ["1.2.3.4"],
                "recordType": "A",
                "setIdentifier": "",
            }
        )
