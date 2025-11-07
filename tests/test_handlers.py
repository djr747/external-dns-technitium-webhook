"""Unit tests for API handlers."""

import json
import re
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.app_state import AppState
from external_dns_technitium_webhook.config import Config
from external_dns_technitium_webhook.handlers import (
    _get_record_data,
    adjust_endpoints,
    apply_record,
    get_records,
    health_check,
    negotiate_domain_filter,
    sanitize_error_message,
)
from external_dns_technitium_webhook.models import (
    AddRecordResponse,
    Changes,
    Endpoint,
    GetRecordsResponse,
    RecordInfo,
    ZoneInfo,
)


@pytest.fixture
def config() -> Config:
    """Create test configuration."""
    return Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="admin",
        zone="example.com",
        domain_filters="sub.example.com",
    )


@pytest.fixture
def app_state(config: Config) -> AppState:
    """Create test application state."""
    state = AppState(config)
    state.is_ready = True
    state.is_writable = True
    state.client.add_record = AsyncMock()  # type: ignore[method-assign]
    state.client.delete_record = AsyncMock()  # type: ignore[method-assign]
    state.client.get_records = AsyncMock()  # type: ignore[method-assign]
    return state


@pytest.mark.asyncio
async def test_health_check_ready(app_state: AppState) -> None:
    """Test health check when ready."""
    response = await health_check(app_state)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_not_ready(app_state: AppState) -> None:
    """Test health check when not ready."""
    app_state.is_ready = False
    response = await health_check(app_state)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_negotiate_domain_filter(app_state: AppState) -> None:
    """Test domain filter negotiation."""
    response = await negotiate_domain_filter(app_state)
    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    data = json.loads(body_bytes.decode())
    filters = data.get("filters", [])
    assert any(f == "sub.example.com" for f in filters)


@pytest.mark.asyncio
async def test_get_records(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting DNS records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="test.example.com",
                type="A",
                ttl=3600,
                rData={"ipAddress": "1.2.3.4"},
            ),
            RecordInfo(
                disabled=False,
                name="caa.example.com",
                type="CAA",
                ttl=3600,
                rData={"flags": 0, "tag": "issue", "value": "letsencrypt.org"},
            ),
            RecordInfo(
                disabled=False,
                name="mx.example.com",
                type="MX",
                ttl=3600,
                rData={"preference": 10, "exchange": "mail.example.com"},
            ),
        ],
    )

    mocker.patch.object(
        app_state.client,
        "get_records",
        return_value=mock_response,
    )

    response = await get_records(app_state)
    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    endpoints = json.loads(body_bytes.decode())
    assert endpoints and endpoints[0]["dnsName"] == "test.example.com"
    assert "1.2.3.4" in endpoints[0].get("targets", [])


@pytest.mark.asyncio
async def test_adjust_endpoints(app_state: AppState) -> None:
    """Test endpoint adjustment."""
    endpoints = [
        Endpoint(
            dnsName="test.example.com",
            targets=["1.2.3.4"],
            recordType="A",
            recordTTL=300,
            setIdentifier="",
        )
    ]

    response = await adjust_endpoints(app_state, endpoints)
    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    endpoints_resp = json.loads(body_bytes.decode())
    assert endpoints_resp and endpoints_resp[0]["dnsName"] == "test.example.com"


@pytest.mark.asyncio
async def test_apply_record_create(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying record creation."""
    mock_response = AddRecordResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        addedRecord=RecordInfo(
            disabled=False,
            name="test.example.com",
            type="A",
            ttl=3600,
            rData={"ipAddress": "1.2.3.4"},
        ),
    )

    mock_add = mocker.patch.object(
        app_state.client,
        "add_record",
        return_value=mock_response,
    )

    changes = Changes(
        create=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    mock_add.assert_called_once()


@pytest.mark.asyncio
async def test_apply_record_delete(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying record deletion."""
    mock_delete = mocker.patch.object(
        app_state.client,
        "delete_record",
    )

    changes = Changes(
        delete=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_apply_record_empty_changes(app_state: AppState) -> None:
    """Test applying empty changes."""
    changes = Changes(updateOld=[], updateNew=[])
    response = await apply_record(app_state, changes)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_sanitize_error_message() -> None:
    """Test error message sanitization."""
    error = Exception("Failed with password=secret123")
    result = sanitize_error_message(error)
    assert re.search(r"password[=:]\*{3}", result)
    assert "secret123" not in result

    error = Exception("Auth failed: token=abc123xyz")
    result = sanitize_error_message(error)
    assert re.search(r"token[=:]\*{3}", result)
    assert "abc123xyz" not in result

    error = Exception("Invalid api_key=12345")
    result = sanitize_error_message(error)
    assert re.search(r"api[_-]?key[=:]\*{3}", result)
    assert "12345" not in result

    error = Exception("Secret: secret=mysecret")
    result = sanitize_error_message(error)
    assert re.search(r"secret[=:]\*{3}", result)
    assert "mysecret" not in result

    error = Exception("File at /home/username/file.txt")
    result = sanitize_error_message(error)
    assert "/home/***" in result
    assert "username" not in result

    error = Exception("Path /Users/john/documents")
    result = sanitize_error_message(error)
    assert "/Users/***" in result
    assert "john" not in result

    error = Exception(r"Path C:\Users\john\documents")
    result = sanitize_error_message(error)
    assert "C:" in result and "Users" in result
    assert "john" not in result


@pytest.mark.asyncio
async def test_get_records_aaaa(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting AAAA records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="test.example.com",
                type="AAAA",
                ttl=3600,
                rData={"ipAddress": "2001:db8::1"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "2001:db8::1"


@pytest.mark.asyncio
async def test_get_records_cname(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting CNAME records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="www.example.com",
                type="CNAME",
                ttl=3600,
                rData={"cname": "example.com"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "example.com"


@pytest.mark.asyncio
async def test_get_records_txt(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting TXT records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
                type="TXT",
                ttl=3600,
                rData={"text": "v=spf1 include:_spf.example.com ~all"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "v=spf1 include:_spf.example.com ~all"


@pytest.mark.asyncio
async def test_get_records_aname(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting ANAME records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
                type="ANAME",
                ttl=3600,
                rData={"aname": "target.example.com"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "target.example.com"


@pytest.mark.asyncio
async def test_get_records_caa(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting CAA records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
                type="CAA",
                ttl=3600,
                rData={"flags": 0, "tag": "issue", "value": "letsencrypt.org"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == '0 issue "letsencrypt.org"'


@pytest.mark.asyncio
async def test_get_records_uri(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting URI records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
                type="URI",
                ttl=3600,
                rData={"priority": 10, "weight": 1, "uri": "https://example.com"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == '10 1 "https://example.com"'


@pytest.mark.asyncio
async def test_get_records_sshfp(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting SSHFP records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="host.example.com",
                type="SSHFP",
                ttl=3600,
                rData={"algorithm": 1, "fingerprintType": 1, "fingerprint": "abc123"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "1 1 abc123"


@pytest.mark.asyncio
async def test_get_records_svcb(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting SVCB records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="_8443._https.api.example.com",
                type="SVCB",
                ttl=3600,
                rData={
                    "svcPriority": 1,
                    "svcTargetName": "svc.example.com",
                    "svcParams": "alpn=h2",
                },
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["dnsName"] == "_8443._https.api.example.com"
    assert data[0]["targets"][0] == "1 svc.example.com alpn=h2"


@pytest.mark.asyncio
async def test_get_records_with_https_record(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting HTTPS records."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
                type="HTTPS",
                ttl=3600,
                rData={"svcPriority": 1, "svcTargetName": ".", "svcParams": "alpn=h3"},
            )
        ],
    )

    mocker.patch.object(app_state.client, "get_records", return_value=mock_response)
    response = await get_records(app_state)
    data = json.loads(bytes(response.body))
    assert data[0]["targets"][0] == "1 . alpn=h3"


@pytest.mark.asyncio
async def test_apply_record_with_updates(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying record updates (old + new)."""
    mock_add = mocker.patch.object(
        app_state.client,
        "add_record",
        return_value=AddRecordResponse(
            zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
            addedRecord=RecordInfo(
                disabled=False,
                name="test.example.com",
                type="A",
                ttl=3600,
                rData={"ipAddress": "1.2.3.5"},
            ),
        ),
    )
    mock_delete = mocker.patch.object(app_state.client, "delete_record")

    changes = Changes(
        updateOld=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateNew=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.5"],
                recordType="A",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    mock_delete.assert_called_once()
    mock_add.assert_called_once()


@pytest.mark.asyncio
async def test_get_record_data_unsupported_type() -> None:
    """Test _get_record_data with an unsupported type."""
    assert _get_record_data("MX", "10 mail.example.com") is None


@pytest.mark.asyncio
async def test_get_record_data_invalid_caa() -> None:
    """Test _get_record_data with invalid CAA record."""
    # Missing parts
    assert _get_record_data("CAA", "1") is None
    # Invalid flags (not integer)
    assert _get_record_data("CAA", 'invalid issue "example.com"') is None


@pytest.mark.asyncio
async def test_get_record_data_a() -> None:
    """Test _get_record_data with A record."""
    ipv4 = "192.0.2.1"
    assert _get_record_data("A", ipv4) == {"ipAddress": ipv4}


@pytest.mark.asyncio
async def test_get_record_data_aaaa() -> None:
    """Test _get_record_data with AAAA record."""
    ipv6 = "2001:db8::1"
    assert _get_record_data("AAAA", ipv6) == {"ipAddress": ipv6}


@pytest.mark.asyncio
async def test_get_record_data_cname() -> None:
    """Test _get_record_data with CNAME record."""
    assert _get_record_data("CNAME", "alias.example.com") == {"cname": "alias.example.com"}


@pytest.mark.asyncio
async def test_get_record_data_txt() -> None:
    """Test _get_record_data with TXT record."""
    assert _get_record_data("TXT", "v=spf1") == {"text": "v=spf1"}


@pytest.mark.asyncio
async def test_get_record_data_aname() -> None:
    """Test _get_record_data with ANAME record."""
    assert _get_record_data("ANAME", "lb.example.com") == {"aname": "lb.example.com"}


@pytest.mark.asyncio
async def test_get_record_data_uri() -> None:
    """Test _get_record_data with URI record."""
    result = _get_record_data("URI", '10 1 "ftp://ftp.example.com/"')
    assert result == {
        "uriPriority": 10,
        "uriWeight": 1,
        "uri": "ftp://ftp.example.com/",
    }


@pytest.mark.asyncio
async def test_get_record_data_sshfp() -> None:
    """Test _get_record_data with SSHFP record."""
    result = _get_record_data("SSHFP", "1 1 da9c419d6757")
    assert result == {"algorithm": 1, "fingerprintType": 1, "fingerprint": "da9c419d6757"}


@pytest.mark.asyncio
async def test_get_record_data_svcb() -> None:
    """Test _get_record_data with SVCB record."""
    result = _get_record_data("SVCB", "1 svc.example.com alpn=h2")
    assert result == {
        "svcPriority": 1,
        "svcTargetName": "svc.example.com",
        "svcParams": "alpn=h2",
    }


@pytest.mark.asyncio
async def test_get_record_data_https() -> None:
    """Test _get_record_data with HTTPS record."""
    result = _get_record_data("HTTPS", "1 . alpn=h3")
    assert result == {"svcPriority": 1, "svcTargetName": ".", "svcParams": "alpn=h3"}


@pytest.mark.asyncio
async def test_get_record_data_invalid_uri() -> None:
    """Test _get_record_data with invalid URI record."""
    assert _get_record_data("URI", "invalid-uri") is None


@pytest.mark.asyncio
async def test_get_record_data_invalid_sshfp() -> None:
    """Test _get_record_data with invalid SSHFP record."""
    assert _get_record_data("SSHFP", "invalid-sshfp") is None


@pytest.mark.asyncio
async def test_get_record_data_invalid_svcb() -> None:
    """Test _get_record_data with invalid SVCB record."""
    assert _get_record_data("SVCB", "invalid-svcb") is None


@pytest.mark.asyncio
async def test_get_record_data_invalid_https() -> None:
    """Test _get_record_data with invalid HTTPS record."""
    assert _get_record_data("HTTPS", "invalid-https") is None


@pytest.mark.asyncio
async def test_get_records_with_uri_record(app_state: AppState, mocker: MockerFixture) -> None:
    """Test get_records with URI record type."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="test.example.com",
                type="URI",
                ttl=3600,
                rData={"uriPriority": 10, "uriWeight": 5, "uri": "http://example.com"},
            )
        ],
    )

    mock_get = mocker.patch.object(
        app_state.client,
        "get_records",
        return_value=mock_response,
    )

    response = await get_records(app_state)
    assert response.status_code == 200
    data = response.body
    assert data is not None
    body_bytes = data.tobytes() if isinstance(data, memoryview) else data or b""
    endpoints_resp = json.loads(body_bytes.decode())
    assert len(endpoints_resp) == 1
    assert endpoints_resp[0]["recordType"] == "URI"
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_apply_record_create_exception(app_state: AppState, mocker: MockerFixture) -> None:
    """Test apply_record create with exception."""
    mock_add = mocker.patch.object(
        app_state.client,
        "add_record",
        side_effect=Exception("Test exception"),
    )

    changes = Changes(
        create=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_record(app_state, changes)

    assert exc_info.value.status_code == 500
    assert "Failed to add record" in str(exc_info.value.detail)
    mock_add.assert_called_once()


@pytest.mark.asyncio
async def test_apply_record_delete_exception(app_state: AppState, mocker: MockerFixture) -> None:
    """Test apply_record delete with exception."""
    mock_delete = mocker.patch.object(
        app_state.client,
        "delete_record",
        side_effect=Exception("Test exception"),
    )

    changes = Changes(
        delete=[
            Endpoint(
                dnsName="test.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await apply_record(app_state, changes)

    assert exc_info.value.status_code == 500
    assert "Failed to delete record" in str(exc_info.value.detail)
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_get_record_data_invalid_ipv4() -> None:
    """Test _get_record_data with invalid IPv4 address."""
    assert _get_record_data("A", "invalid.ip") is None


@pytest.mark.asyncio
async def test_get_record_data_invalid_ipv6() -> None:
    """Test _get_record_data with invalid IPv6 address."""
    assert _get_record_data("AAAA", "invalid:ipv6") is None


@pytest.mark.asyncio
async def test_apply_record_create_invalid_record_data(
    app_state: AppState, mocker: MockerFixture
) -> None:
    """Test apply_record create with invalid record data."""
    mock_add = mocker.patch.object(
        app_state.client,
        "add_record",
    )

    changes = Changes(
        create=[
            Endpoint(
                dnsName="test.example.com",
                targets=["invalid.ip"],  # Invalid IPv4
                recordType="A",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    # Should not call add_record due to invalid data
    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_apply_record_delete_invalid_record_data(
    app_state: AppState, mocker: MockerFixture
) -> None:
    """Test apply_record delete with invalid record data."""
    mock_delete = mocker.patch.object(
        app_state.client,
        "delete_record",
    )

    changes = Changes(
        delete=[
            Endpoint(
                dnsName="test.example.com",
                targets=["invalid.ip"],  # Invalid IPv4
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    # Should not call delete_record due to invalid data
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_apply_record_create_caa_record(app_state: AppState, mocker: MockerFixture) -> None:
    """Test apply_record create with CAA record."""
    mock_add = mocker.patch.object(
        app_state.client,
        "add_record",
    )

    changes = Changes(
        create=[
            Endpoint(
                dnsName="caa.example.com",
                targets=['0 issue "letsencrypt.org"'],  # Valid CAA format
                recordType="CAA",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204
    mock_add.assert_called_once()
