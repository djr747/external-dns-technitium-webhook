"""Unit tests for API handlers."""

import pytest
import json
import re
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
)
from external_dns_technitium_webhook.models import (
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
    with pytest.raises(HTTPException) as exc_info:
        await health_check(app_state)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_negotiate_domain_filter(app_state: AppState) -> None:
    """Test domain filter negotiation."""
    response = await negotiate_domain_filter(app_state)
    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    data = json.loads(body_bytes.decode())
    assert "sub.example.com" in data.get("filters", [])


@pytest.mark.asyncio
async def test_get_records(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting DNS records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="test.example.com",
                type="A",
                ttl=3600,
                rData={"ipAddress": "1.2.3.4"},
            )
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
    assert "1.2.3.4" in endpoints[0].get("targets", [])[0]


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
    from external_dns_technitium_webhook.models import (
        AddRecordResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    from external_dns_technitium_webhook.handlers import sanitize_error_message

    # Test password redaction
    error = Exception("Failed with password=secret123")
    result = sanitize_error_message(error)
    assert re.search(r"password[=:]\*{3}", result)
    assert "secret123" not in result

    # Test token redaction
    error = Exception("Auth failed: token=abc123xyz")
    result = sanitize_error_message(error)
    assert re.search(r"token[=:]\*{3}", result)
    assert "abc123xyz" not in result

    # Test API key redaction
    error = Exception("Invalid api_key=12345")
    result = sanitize_error_message(error)
    assert re.search(r"api[_-]?key[=:]\*{3}", result)
    assert "12345" not in result

    # Test secret redaction
    error = Exception("Secret: secret=mysecret")
    result = sanitize_error_message(error)
    assert re.search(r"secret[=:]\*{3}", result)
    assert "mysecret" not in result

    # Test home path redaction
    error = Exception("File at /home/username/file.txt")
    result = sanitize_error_message(error)
    assert "/home/***" in result
    assert "username" not in result

    # Test Users path redaction (Unix)
    error = Exception("Path /Users/john/documents")
    result = sanitize_error_message(error)
    assert "/Users/***" in result
    assert "john" not in result

    # Test Windows Users path redaction
    error = Exception(r"Path C:\Users\john\documents")
    result = sanitize_error_message(error)
    # Windows backslashes will be escaped in the string; ensure redaction token present and username removed
    assert "C:" in result and "Users" in result
    assert "john" not in result


@pytest.mark.asyncio
async def test_get_records_aaaa(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting AAAA records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "2001:db8::1" in data


@pytest.mark.asyncio
async def test_get_records_cname(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting CNAME records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "example.com" in data


@pytest.mark.asyncio
async def test_get_records_txt(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting TXT records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "v=spf1" in data


@pytest.mark.asyncio
async def test_get_records_aname(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting ANAME records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "target.example.com" in data


@pytest.mark.asyncio
async def test_get_records_caa(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting CAA records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "letsencrypt.org" in data


@pytest.mark.asyncio
async def test_get_records_uri(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting URI records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "https://example.com" in data


@pytest.mark.asyncio
async def test_get_records_sshfp(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting SSHFP records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "abc123" in data


@pytest.mark.asyncio
async def test_get_records_svcb(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting SVCB records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="example.com",
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
    data = bytes(response.body).decode()
    assert "svc.example.com" in data


@pytest.mark.asyncio
async def test_get_records_https(app_state: AppState, mocker: MockerFixture) -> None:
    """Test getting HTTPS records."""
    from external_dns_technitium_webhook.models import (
        GetRecordsResponse,
        RecordInfo,
        ZoneInfo,
    )

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
    data = bytes(response.body).decode()
    assert "alpn=h3" in data


@pytest.mark.asyncio
async def test_apply_record_with_updates(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying record updates (old + new)."""
    from external_dns_technitium_webhook.models import (
        AddRecordResponse,
        RecordInfo,
        ZoneInfo,
    )

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
                recordTTL=3600,
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
async def test_apply_record_delete_error(app_state: AppState, mocker: MockerFixture) -> None:
    """Test error handling during record deletion."""
    mocker.patch.object(app_state.client, "delete_record", side_effect=Exception("Delete failed"))

    changes = Changes(
        delete=[
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
    assert "Failed to delete record" in exc_info.value.detail


@pytest.mark.asyncio
async def test_apply_record_add_error(app_state: AppState, mocker: MockerFixture) -> None:
    """Test error handling during record addition."""
    mocker.patch.object(app_state.client, "add_record", side_effect=Exception("Add failed"))

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
    assert "Failed to add record" in exc_info.value.detail


@pytest.mark.asyncio
async def test_apply_record_invalid_ipv4(app_state: AppState, mocker: MockerFixture) -> None:
    """Test handling of invalid IPv4 addresses."""
    # Should skip invalid IPs and return success
    changes = Changes(
        create=[
            Endpoint(
                dnsName="test.example.com",
                targets=["999.999.999.999"],  # Invalid IP
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


@pytest.mark.asyncio
async def test_apply_record_invalid_ipv6(app_state: AppState, mocker: MockerFixture) -> None:
    """Test handling of invalid IPv6 addresses."""
    # Should skip invalid IPs and return success
    changes = Changes(
        create=[
            Endpoint(
                dnsName="test.example.com",
                targets=["gggg::1"],  # Invalid IPv6
                recordType="AAAA",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_apply_record_caa(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying CAA records."""
    mock_add = mocker.patch.object(app_state.client, "add_record")

    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=['0 issue "letsencrypt.org"'],
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


@pytest.mark.asyncio
async def test_apply_record_uri(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying URI records."""
    mock_add = mocker.patch.object(app_state.client, "add_record")

    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=['10 1 "https://example.com"'],
                recordType="URI",
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
async def test_apply_record_sshfp(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying SSHFP records."""
    mock_add = mocker.patch.object(app_state.client, "add_record")

    changes = Changes(
        create=[
            Endpoint(
                dnsName="host.example.com",
                targets=["1 1 abc123def456"],
                recordType="SSHFP",
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
async def test_apply_record_svcb(app_state: AppState, mocker: MockerFixture) -> None:
    """Test applying SVCB records."""
    mock_add = mocker.patch.object(app_state.client, "add_record")

    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=["1 svc.example.com alpn=h2"],
                recordType="SVCB",
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
async def test_apply_record_invalid_caa_format(app_state: AppState, mocker: MockerFixture) -> None:
    """Test handling of invalid CAA record format."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=["invalid"],  # Missing required parts
                recordType="CAA",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204  # Skips invalid records


@pytest.mark.asyncio
async def test_apply_record_invalid_uri_format(app_state: AppState, mocker: MockerFixture) -> None:
    """Test handling of invalid URI record format."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=["10"],  # Missing weight and URI
                recordType="URI",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204  # Skips invalid records


@pytest.mark.asyncio
async def test_apply_record_invalid_svcb_format(app_state: AppState, mocker: MockerFixture) -> None:
    """Test handling of invalid SVCB record format."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=["1"],  # Missing target
                recordType="SVCB",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204  # Skips invalid records


@pytest.mark.asyncio
async def test_get_records_unsupported_type(app_state: AppState, mocker: MockerFixture) -> None:
    """Test that unsupported record types are skipped."""
    mock_response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name="test.example.com",
                type="MX",  # Unsupported record type
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
    assert response.status_code == 200

    # Unsupported type should be skipped
    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    data = body_bytes.decode()
    import json

    endpoints = json.loads(data)
    assert len(endpoints) == 0  # MX record was skipped


@pytest.mark.asyncio
async def test_apply_record_invalid_sshfp_format(
    app_state: AppState, mocker: MockerFixture
) -> None:
    """Test handling of invalid SSHFP record format."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="example.com",
                targets=["1 2"],  # Missing fingerprint
                recordType="SSHFP",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204  # Skips invalid records


@pytest.mark.asyncio
async def test_apply_record_delete_invalid_type(app_state: AppState, mocker: MockerFixture) -> None:
    """Test deletion with invalid record type is skipped."""
    changes = Changes(
        delete=[
            Endpoint(
                dnsName="test.example.com",
                targets=["invalid"],
                recordType="INVALID_TYPE",
                recordTTL=3600,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    response = await apply_record(app_state, changes)
    assert response.status_code == 204  # Skips invalid records


def test_get_record_data_caa_parses_fields() -> None:
    """CAA helper should parse composite fields into structured data."""
    result = _get_record_data("CAA", '0 issue "letsencrypt.org"')
    assert result == {"flags": 0, "tag": "issue", "value": "letsencrypt.org"}


def test_get_record_data_aaaa_returns_ipv6() -> None:
    """AAAA helper should return IPv6 address data."""
    ipv6 = "2001:db8::1"
    assert _get_record_data("AAAA", ipv6) == {"ipAddress": ipv6}


def test_get_record_data_cname_returns_target() -> None:
    """CNAME helper should wrap the alias value."""
    assert _get_record_data("CNAME", "alias.example.com") == {"cname": "alias.example.com"}


def test_get_record_data_txt_returns_text() -> None:
    """TXT helper should wrap the provided string."""
    assert _get_record_data("TXT", "v=spf1") == {"text": "v=spf1"}


def test_get_record_data_aname_returns_target() -> None:
    """ANAME helper should map to Technitium field name."""
    assert _get_record_data("ANAME", "lb.example.com") == {"aname": "lb.example.com"}
