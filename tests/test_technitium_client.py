"""Unit tests for Technitium client."""

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.models import CreateZoneResponse
from external_dns_technitium_webhook.technitium_client import (
    InvalidTokenError,
    TechnitiumClient,
    TechnitiumError,
)


@pytest.fixture
def client() -> TechnitiumClient:
    """Create a test client."""
    return TechnitiumClient(base_url="http://localhost:5380", token="test-token")


@pytest.mark.asyncio
async def test_client_login_success(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test successful login."""
    mock_response = {
        "status": "ok",
        "displayName": "Admin",
        "username": "admin",
        "token": "new-token",
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.login("admin", "password")

    assert response.token == "new-token"
    assert response.username == "admin"
    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_client_login_error(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test login error."""
    mock_response = {
        "status": "error",
        "errorMessage": "Invalid credentials",
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(TechnitiumError, match="Invalid credentials"):
        await client.login("admin", "wrong-password")


@pytest.mark.asyncio
async def test_client_login_error_includes_stack_trace(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """Technitium errors should capture stack trace and inner error details."""

    mock_response = {
        "status": "error",
        "errorMessage": "Database connection failed",
        "stackTrace": "at DatabaseConnection.connect()",
        "innerErrorMessage": "Timeout waiting for connection",
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(TechnitiumError) as exc_info:
        await client.login("admin", "password")

    error = exc_info.value
    assert error.error_message == "Database connection failed"
    assert error.stack_trace == "at DatabaseConnection.connect()"
    assert error.inner_error == "Timeout waiting for connection"
    assert "Database connection failed" in str(error)


@pytest.mark.asyncio
async def test_client_create_zone(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test zone creation."""
    mock_response = {
        "status": "ok",
        "response": {
            "domain": "example.com",
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.create_zone(zone="example.com")
    assert response.domain == "example.com"


@pytest.mark.asyncio
async def test_client_add_record(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test adding a record."""
    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": False,
                "name": "test.example.com",
                "type": "A",
                "ttl": 3600,
                "rData": {"ipAddress": "1.2.3.4"},
            },
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="test.example.com",
        record_type="A",
        record_data={"ipAddress": "1.2.3.4"},
        ttl=3600,
    )

    assert response.added_record.name == "test.example.com"
    assert response.added_record.type == "A"


@pytest.mark.asyncio
async def test_client_add_aname_record(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """add_record should support Technitium ANAME records."""

    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": False,
                "name": "www.example.com",
                "type": "ANAME",
                "ttl": 3600,
                "rData": {"aname": "target.example.com"},
                "dnssecStatus": "Unknown",
            },
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="www.example.com",
        record_type="ANAME",
        record_data={"aname": "target.example.com"},
        ttl=3600,
    )

    assert response.added_record.type == "ANAME"
    assert response.added_record.r_data["aname"] == "target.example.com"


@pytest.mark.asyncio
async def test_client_add_caa_record(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """add_record should handle CAA payloads."""

    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": False,
                "name": "example.com",
                "type": "CAA",
                "ttl": 3600,
                "rData": {
                    "flags": 0,
                    "tag": "issue",
                    "value": "letsencrypt.org",
                },
                "dnssecStatus": "Unknown",
            },
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="example.com",
        record_type="CAA",
        record_data={"flags": 0, "tag": "issue", "value": "letsencrypt.org"},
        ttl=3600,
    )

    assert response.added_record.type == "CAA"
    assert response.added_record.r_data["tag"] == "issue"


@pytest.mark.asyncio
async def test_client_context_manager(mocker: MockerFixture) -> None:
    """Test client as context manager."""
    async with TechnitiumClient(base_url="http://localhost:5380", token="test-token") as client:
        assert client is not None

    # Client should be closed after exiting context


@pytest.mark.asyncio
async def test_post_json_parse_error(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test JSON parse error in _post method."""
    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(side_effect=ValueError("Invalid JSON")),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(TechnitiumError, match="Failed to parse JSON response"):
        await client.login("admin", "password")


@pytest.mark.asyncio
async def test_post_http_status_error(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test HTTP status error in _post method."""
    import httpx

    mock_response = mocker.Mock(status_code=500)
    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            raise_for_status=mocker.Mock(
                side_effect=httpx.HTTPStatusError(
                    "Server error", request=mocker.Mock(), response=mock_response
                )
            ),
        ),
    )

    with pytest.raises(TechnitiumError, match="Server responded with status code 500"):
        await client.login("admin", "password")


@pytest.mark.asyncio
async def test_post_request_error(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test request error in _post method."""
    import httpx

    mocker.patch.object(
        client._client,
        "post",
        side_effect=httpx.RequestError("Connection failed"),
    )

    with pytest.raises(TechnitiumError, match="Request error"):
        await client.login("admin", "password")


@pytest.mark.asyncio
async def test_list_zones_with_pagination(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test list_zones with pagination parameters."""
    mock_response = {
        "status": "ok",
        "response": {
            "pageNumber": 2,
            "totalPages": 5,
            "totalZones": 50,
            "zones": [
                {"name": "example.com", "type": "Primary", "disabled": False},
            ],
        },
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.list_zones(zone="example.com", page_number=2, zones_per_page=10)

    assert response.page_number == 2
    assert response.total_pages == 5
    # Verify the call included pagination parameters
    call_args = mock_post.call_args
    assert call_args[1]["data"]["pageNumber"] == 2
    assert call_args[1]["data"]["zonesPerPage"] == 10


@pytest.mark.asyncio
async def test_add_record_with_all_options(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test add_record with all optional parameters."""
    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": True,
                "name": "test.example.com",
                "type": "A",
                "ttl": 7200,
                "rData": {"ipAddress": "1.2.3.4"},
                "comments": "Test comment",
            },
        },
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="test.example.com",
        record_type="A",
        record_data={"ipAddress": "1.2.3.4"},
        ttl=7200,
        zone="example.com",
        comments="Test comment",
        expiry_ttl=86400,
        disabled=True,
        overwrite=True,
        ptr=True,
        create_ptr_zone=True,
        update_svcb_hints=True,
    )

    assert response.added_record.name == "test.example.com"

    # Verify all optional parameters were passed
    call_args = mock_post.call_args
    payload = call_args[1]["data"]
    assert payload["comments"] == "Test comment"
    assert payload["expiryTtl"] == 86400
    assert payload["disable"] == "true"
    assert payload["overwrite"] == "true"
    assert payload["ptr"] == "true"
    assert payload["createPtrZone"] == "true"
    assert payload["updateSvcbHints"] == "true"


@pytest.mark.asyncio
async def test_client_add_uri_record(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """add_record should serialize URI record data fields."""

    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": False,
                "name": "_http._tcp.example.com",
                "type": "URI",
                "ttl": 3600,
                "rData": {
                    "priority": 10,
                    "weight": 50,
                    "uri": "https://example.com/path",
                },
                "dnssecStatus": "Unknown",
            },
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="_http._tcp.example.com",
        record_type="URI",
        record_data={
            "uriPriority": 10,
            "uriWeight": 50,
            "uri": "https://example.com/path",
        },
        ttl=3600,
    )

    assert response.added_record.type == "URI"
    assert response.added_record.r_data["priority"] == 10


@pytest.mark.asyncio
async def test_client_add_svcb_record(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """add_record should honor SVCB hint settings."""

    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "addedRecord": {
                "disabled": False,
                "name": "example.com",
                "type": "SVCB",
                "ttl": 3600,
                "rData": {
                    "svcPriority": 1,
                    "svcTargetName": ".",
                    "svcParams": "alpn=h3,h2",
                    "autoIpv4Hint": True,
                    "autoIpv6Hint": True,
                },
                "dnssecStatus": "Unknown",
            },
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.add_record(
        domain="example.com",
        record_type="SVCB",
        record_data={
            "svcPriority": 1,
            "svcTargetName": ".",
            "svcParams": "alpn=h3,h2",
            "autoIpv4Hint": True,
            "autoIpv6Hint": True,
        },
        ttl=3600,
    )

    assert response.added_record.type == "SVCB"
    assert response.added_record.r_data["autoIpv4Hint"] is True


@pytest.mark.asyncio
async def test_post_invalid_token_status(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test invalid-token status in _post method."""
    mock_response = {
        "status": "invalid-token",
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(InvalidTokenError, match="Invalid or expired token"):
        await client.login("admin", "password")


@pytest.mark.asyncio
async def test_create_zone_invalid_token_error(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """create_zone should propagate invalid token responses."""

    mock_response = {
        "status": "invalid-token",
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(InvalidTokenError, match="Invalid or expired token"):
        await client.create_zone(zone="example.com")


@pytest.mark.asyncio
async def test_get_records_with_optional_params(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """Test get_records with optional zone and list_zone parameters."""
    mock_response = {
        "status": "ok",
        "response": {
            "zone": {
                "name": "example.com",
                "type": "Primary",
                "disabled": False,
            },
            "records": [],
        },
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.get_records(
        domain="test.example.com", zone="example.com", list_zone=True
    )

    assert response.zone.name == "example.com"

    # Verify optional parameters were passed
    call_args = mock_post.call_args
    payload = call_args[1]["data"]
    assert payload["zone"] == "example.com"
    assert payload["listZone"] == "true"


@pytest.mark.asyncio
async def test_delete_record_with_zone(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test delete_record with optional zone parameter."""
    mock_response = {
        "status": "ok",
        "response": {},
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    await client.delete_record(
        domain="test.example.com",
        record_type="A",
        record_data={"ipAddress": "1.2.3.4"},
        zone="example.com",
    )

    # Verify zone parameter was passed
    call_args = mock_post.call_args
    payload = call_args[1]["data"]
    assert payload["zone"] == "example.com"
    assert payload["domain"] == "test.example.com"
    assert payload["type"] == "A"


@pytest.mark.asyncio
async def test_post_raw_unexpected_response_format(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """_post_raw should reject responses that are not dictionaries."""

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=[]),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(TechnitiumError, match="Unexpected response format"):
        await client._post_raw("/test", {})


@pytest.mark.asyncio
async def test_post_raw_unexpected_status(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """_post_raw should raise when status is unrecognised."""

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value={"status": "weird"}),
            raise_for_status=mocker.Mock(),
        ),
    )

    with pytest.raises(TechnitiumError, match="Unexpected response status"):
        await client._post_raw("/test", {})


class _DummyResponse(BaseModel):
    """Simple model for exercising private client helpers."""

    value: int = 0


@pytest.mark.asyncio
async def test_post_allows_missing_response_payload(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """_post should treat a missing response payload as an empty mapping."""

    mocker.patch.object(
        client,
        "_post_raw",
        new_callable=AsyncMock,
        return_value={"status": "ok", "response": None},
    )

    result = await client._post("/test", {"foo": "bar"}, _DummyResponse)
    assert isinstance(result, _DummyResponse)
    assert result.value == 0


@pytest.mark.asyncio
async def test_post_rejects_non_mapping_response(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """_post should raise when response payload is not a mapping."""

    mocker.patch.object(
        client,
        "_post_raw",
        new_callable=AsyncMock,
        return_value={"status": "ok", "response": []},
    )

    with pytest.raises(TechnitiumError, match="Unexpected response payload format"):
        await client._post("/test", {"foo": "bar"}, _DummyResponse)


@pytest.mark.asyncio
async def test_create_zone_includes_optional_arguments(
    client: TechnitiumClient, mocker: MockerFixture
) -> None:
    """create_zone should serialize optional and extra arguments correctly."""

    mock_post = mocker.patch.object(
        client,
        "_post",
        new_callable=AsyncMock,
        return_value=CreateZoneResponse(domain="example.com"),
    )

    await client.create_zone(
        zone="example.com",
        catalog="catalog.example.com",
        allowNotify=False,
        description=None,
        customOption="value",
    )

    call = mock_post.await_args
    assert call is not None
    payload = call.args[1]

    assert payload["catalog"] == "catalog.example.com"
    assert payload["allowNotify"] == "false"
    assert "description" not in payload
    assert payload["customOption"] == "value"


@pytest.mark.asyncio
async def test_list_catalog_zones(client: TechnitiumClient, mocker: MockerFixture) -> None:
    """Test listing catalog zones."""

    mock_response = {
        "status": "ok",
        "response": {
            "catalogZones": ["catalog.example.com", "other.example.com"],
        },
    }

    mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    response = await client.list_catalog_zones()
    assert response.catalog_zones == ["catalog.example.com", "other.example.com"]


@pytest.mark.asyncio
async def test_get_zone_options_with_catalog_names(
    client: TechnitiumClient,
    mocker: MockerFixture,
) -> None:
    """get_zone_options should include optional catalog listing flag."""

    mock_response = {
        "status": "ok",
        "response": {
            "zone": "example.com",
            "isCatalogZone": False,
            "isReadOnly": False,
            "catalogZoneName": None,
            "availableCatalogZoneNames": ["catalog.example.com"],
        },
    }

    mock_post = mocker.patch.object(
        client._client,
        "post",
        return_value=mocker.Mock(
            status_code=200,
            json=mocker.Mock(return_value=mock_response),
            raise_for_status=mocker.Mock(),
        ),
    )

    await client.get_zone_options("example.com", include_catalog_names=True)

    payload = mock_post.call_args[1]["data"]
    assert payload["includeAvailableCatalogZoneNames"] == "true"


@pytest.mark.asyncio
async def test_set_zone_options_serializes_values(
    client: TechnitiumClient,
    mocker: MockerFixture,
) -> None:
    """set_zone_options should serialize bools and lists appropriately."""

    post_raw = mocker.patch.object(client, "_post_raw", new_callable=AsyncMock)

    await client.set_zone_options(
        "example.com",
        notifySecondaries=True,
        maxTransfers=5,
        allowedIpRanges=["192.0.2.1", "2001:db8::1"],
        description=None,
    )

    post_raw.assert_awaited_once()
    await_args = post_raw.await_args
    assert await_args is not None
    endpoint, payload = await_args.args
    assert endpoint == client.ENDPOINT_SET_ZONE_OPTIONS
    assert payload["zone"] == "example.com"
    assert payload["notifySecondaries"] == "true"
    assert payload["maxTransfers"] == 5
    assert payload["allowedIpRanges"] == "192.0.2.1,2001:db8::1"
    assert "description" not in payload


def test_client_init_with_verify_ssl_false() -> None:
    """Test client initialization with verify_ssl=False."""
    client = TechnitiumClient(
        base_url="http://localhost:5380",
        token="test-token",
        verify_ssl=False,
    )
    assert client.verify_ssl is False


def test_client_init_with_ca_bundle() -> None:
    """Test client initialization with CA bundle."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        ca_file = f"{tmpdir}/ca.pem"
        # Create a valid self-signed CA certificate
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

        client = TechnitiumClient(
            base_url="http://localhost:5380",
            token="test-token",
            verify_ssl=True,
            ca_bundle=ca_file,
        )
        # When ca_bundle is provided, it should be stored
        assert client.ca_bundle == ca_file


def test_client_init_default_verify_ssl() -> None:
    """Test client initialization with default verify_ssl (True)."""
    client = TechnitiumClient(
        base_url="http://localhost:5380",
        token="test-token",
    )
    assert client.verify_ssl is True
    assert client.ca_bundle is None
