"""Unit tests for API handlers."""

import json
import logging
import re
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.app_state import AppState
from external_dns_technitium_webhook.config import Config
from external_dns_technitium_webhook.handlers import (
    _execute_change,
    _get_record_data,
    _record_stream,
    _process_changes,
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
from external_dns_technitium_webhook.resilience import CircuitBreakerOpenError, CircuitState


class TestGetRecordsErrorHandling:
    """Test error handling in get_records handler."""


class TestAdjustEndpointsErrorHandling:
    """Test error handling in adjust_endpoints handler."""

    @pytest.mark.asyncio
    async def test_adjust_endpoints_payload_logging_failure(self, mock_state, mocker, caplog):
        """Test adjust_endpoints when payload logging fails."""
        # Mock safe_log_payload to raise an exception
        mocker.patch(
            "external_dns_technitium_webhook.handlers.safe_log_payload",
            side_effect=Exception("Payload logging failed"),
        )

        endpoints = [
            Endpoint(
                dnsName="test.example.com",
                recordType="A",
                recordTTL=300,
                setIdentifier="",
                targets=["192.0.2.1"],
            )
        ]

        with caplog.at_level(logging.DEBUG):
            result = await adjust_endpoints(mock_state, endpoints)

        # Should still return successfully despite logging failure
        assert result is not None
        # Should log the debug message about failure
        assert "Failed to log adjust_endpoints payload" in caplog.text


class TestApplyRecordErrorHandling:
    """Test error handling in apply_record handler."""

    @pytest.mark.asyncio
    async def test_apply_record_payload_logging_failure(self, mock_state, mocker, caplog):
        """Test apply_record when Changes payload logging fails."""
        # Mock safe_log_payload to raise an exception
        mocker.patch(
            "external_dns_technitium_webhook.handlers.safe_log_payload",
            side_effect=Exception("Payload logging failed"),
        )

        # Mock client methods
        mock_state.client.delete_record = AsyncMock()
        mock_state.client.add_record = AsyncMock()

        changes = Changes(
            create=[
                Endpoint(
                    dnsName="test.example.com",
                    recordType="A",
                    recordTTL=300,
                    setIdentifier="",
                    targets=["192.0.2.1"],
                )
            ],
            delete=[],
            updateOld=[],
            updateNew=[],
        )

        with caplog.at_level(logging.INFO):
            result = await apply_record(mock_state, changes)

        # Should still process changes despite logging failure
        assert result is not None
        # Should log the failure at INFO level
        assert "apply_record received Changes object (failed to serialize)" in caplog.text


async def collect_streaming_response(response) -> bytes:
    """Collect the content of a StreamingResponse or Response for testing."""
    if hasattr(response, "body_iterator"):
        # StreamingResponse
        content = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                content += chunk.encode()
            else:
                content += chunk
        return content
    else:
        # Regular Response
        raw_body = response.body
        return raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""


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
def app_state(config: Config, mocker: MockerFixture) -> AppState:
    """Create test application state."""
    state = AppState(config)
    state.is_ready = True
    state.is_writable = True
    mocker.patch.object(state.client, "add_record", new=AsyncMock())
    mocker.patch.object(state.client, "delete_record", new=AsyncMock())
    mocker.patch.object(state.client, "get_records", new=AsyncMock())
    return state


@pytest.fixture
def mock_state(mocker):
    """Create a mock AppState for error handling tests."""
    state = AsyncMock(spec=AppState)
    state.ensure_ready = AsyncMock()
    state.ensure_writable = AsyncMock()
    state.client = AsyncMock()
    state.config = MagicMock()
    state.config.zone = "example.com"
    state.record_fetch_count = 0
    return state


@pytest.fixture
def mock_request():
    """Create a mock Request for header logging tests."""
    request = MagicMock(spec=Request)
    request.headers = {"Accept-Encoding": "gzip", "User-Agent": "ExternalDNS"}
    return request


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
    body_bytes = await collect_streaming_response(response)
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


# new tests for coverage gaps

@pytest.mark.asyncio
async def test_record_stream_skips_ignored_types_and_emits_commas() -> None:
    """Verify that the streaming generator emits JSON entries and commas.

    We construct a simple GetRecordsResponse containing two records of a
    non-skipped type.  The output should start with ``[`` and end with
    ``]`` and include a comma between the two serialized endpoints.
    """
    from external_dns_technitium_webhook.models import RecordInfo, ZoneInfo, GetRecordsResponse

    # include one ignored type (MX) plus two valid ones to exercise both
    # the skipping logic and the comma insertion.
    records = [
        RecordInfo(disabled=False, name="foo.example", ttl=300, type="A", rData={"A": "1.2.3.4"}),
        RecordInfo(disabled=False, name="skip.example", ttl=300, type="MX", rData={"mx": "mail"}),
        RecordInfo(disabled=False, name="bar.example", ttl=300, type="ANAME", rData={"aname": "alias"}),
    ]
    resp = GetRecordsResponse(zone=ZoneInfo(name="example.com", type="primary", internal=False, disabled=False), records=records)

    chunks: list[str] = []
    async for chunk in _record_stream(resp):
        chunks.append(chunk)

    assert chunks[0] == "["
    assert chunks[-1] == "]"
    # ensure the ignored record never made it into the output
    assert all("skip.example" not in chunk for chunk in chunks)
    # since there are two valid endpoints, a comma must be inserted
    assert "," in chunks


@pytest.mark.asyncio
async def test_process_changes_skips_unsupported_type(app_state: AppState, caplog):
    """When _get_record_data returns ``None`` a warning is logged and no
    client call is made.
    """
    ep = Endpoint(
        dnsName="bad.example.com",
        targets=["ignored"],
        recordType="MX",  # unsupported type
        recordTTL=60,
        setIdentifier="",
    )

    caplog.set_level(logging.WARNING)
    await _process_changes(app_state, [ep], "create")

    # client should never be invoked
    app_state.client.add_record.assert_not_awaited()
    assert "Skipping creation" in caplog.text


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


# tests for the internal helper introduced during refactoring
@pytest.mark.asyncio
async def test_execute_change_success(app_state: AppState) -> None:
    """The helper should invoke the correct client method and increment metrics."""
    ep = Endpoint(
        dnsName="foo.example.com",
        targets=["1.2.3.4"],
        recordType="A",
        recordTTL=300,
        setIdentifier="",
    )
    record_data = {"ipAddress": "1.2.3.4"}

    await _execute_change(app_state, ep, record_data, "create")
    app_state.client.add_record.assert_awaited_once_with(  # type: ignore[reportAttributeAccessIssue]
        domain="foo.example.com",
        record_type="A",
        record_data=record_data,
        ttl=300,
    )

    # deletion path
    await _execute_change(app_state, ep, record_data, "delete")
    app_state.client.delete_record.assert_awaited_once_with(  # type: ignore[reportAttributeAccessIssue]
        domain="foo.example.com",
        record_type="A",
        record_data=record_data,
    )


@pytest.mark.asyncio
async def test_execute_change_circuit_open(app_state: AppState) -> None:
    """Circuit breaker errors should translate to 503 HTTPException."""
    from external_dns_technitium_webhook.handlers import API_UNAVAILABLE

    ep = Endpoint(
        dnsName="bar.example.com",
        targets=["1.2.3.5"],
        recordType="A",
        recordTTL=60,
        setIdentifier="",
    )
    record_data = {"ipAddress": "1.2.3.5"}

    # instantiate with dummy state value to satisfy constructor
    app_state.client.add_record = AsyncMock(
        side_effect=CircuitBreakerOpenError(CircuitState.OPEN, retry_after=5)
    )
    with pytest.raises(HTTPException) as excinfo:
        await _execute_change(app_state, ep, record_data, "create")

    assert excinfo.value.status_code == 503
    assert API_UNAVAILABLE in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_apply_record_delete_circuit_open(mock_state, mocker):
    """Delete operation should surface circuit-open as 503 with Retry-After."""
    # Prepare a deletion change
    changes = Changes(
        delete=[
            Endpoint(
                dnsName="delete.example.com",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    cboe = CircuitBreakerOpenError(CircuitState.OPEN, 7)
    mock_state.client.delete_record = mocker.AsyncMock(side_effect=cboe)

    with pytest.raises(HTTPException) as exc:
        await apply_record(mock_state, changes)

    # Should raise HTTPException with 503
    assert exc.value.status_code == 503
    assert exc.value.headers is not None
    assert exc.value.headers.get("Retry-After") == "7"


@pytest.mark.asyncio
async def test_apply_record_delete_exception(mock_state, mocker):
    """Generic delete failure should result in 500 and sanitized message."""
    changes = Changes(
        delete=[
            Endpoint(
                dnsName="delete.fail",
                targets=["1.2.3.4"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    mock_state.client.delete_record = mocker.AsyncMock(side_effect=Exception("password=sekrit"))

    with pytest.raises(HTTPException) as exc:
        await apply_record(mock_state, changes)

    assert exc.value.status_code == 500
    assert "Failed to delete record" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_apply_record_add_circuit_open(mock_state, mocker):
    """Add operation should surface circuit-open as 503 with Retry-After."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="add.example.com",
                targets=["1.2.3.5"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    cboe = CircuitBreakerOpenError(CircuitState.OPEN, 4)
    mock_state.client.add_record = mocker.AsyncMock(side_effect=cboe)

    with pytest.raises(HTTPException) as exc:
        await apply_record(mock_state, changes)

    assert exc.value.status_code == 503
    assert exc.value.headers is not None
    assert exc.value.headers.get("Retry-After") == "4"


@pytest.mark.asyncio
async def test_apply_record_add_exception(mock_state, mocker):
    """Generic add failure should result in 500 and sanitized message."""
    changes = Changes(
        create=[
            Endpoint(
                dnsName="add.fail",
                targets=["1.2.3.5"],
                recordType="A",
                recordTTL=300,
                setIdentifier="",
            )
        ],
        updateOld=[],
        updateNew=[],
    )

    mock_state.client.add_record = mocker.AsyncMock(side_effect=Exception("token=abc123"))

    with pytest.raises(HTTPException) as exc:
        await apply_record(mock_state, changes)

    assert exc.value.status_code == 500
    assert "Failed to create record" in str(exc.value.detail)


# Additional tests merged from test_handlers_extra.py


class DummyResponse:
    def __init__(self, records):
        self.records = records


@pytest.mark.asyncio
async def test_get_records_circuit_open(mocker):
    class DummyState:
        is_ready = True

        async def ensure_ready(self):
            return None

        config = type("C", (), {"zone": "example.com"})

        client = mocker.Mock()

    # Simulate circuit open error with retry_after
    cboe = CircuitBreakerOpenError(CircuitState.OPEN, 5)
    state = DummyState()
    state.client.get_records = mocker.AsyncMock(side_effect=cboe)

    with pytest.raises(HTTPException) as exc:
        await get_records(cast(AppState, state))

    assert exc.value.status_code == 503
    assert exc.value.headers is not None
    assert exc.value.headers.get("Retry-After") == "5"


def test_get_record_data_variants_additional():
    # CAA valid
    data = _get_record_data("CAA", '0 issue "ca.example"')
    assert data == {"flags": 0, "tag": "issue", "value": "ca.example"}

    # CAA invalid (missing parts)
    assert _get_record_data("CAA", "invalid") is None

    # URI valid
    data_uri = _get_record_data("URI", '10 20 "https://example.com"')
    assert data_uri is not None
    assert data_uri == {"uriPriority": 10, "uriWeight": 20, "uri": "https://example.com"}

    # SSHFP valid
    data_sshfp = _get_record_data("SSHFP", "1 1 abcdef")
    assert data_sshfp is not None
    assert data_sshfp["algorithm"] == 1

    # SVCB/HTTPS valid
    data_svcb = _get_record_data("SVCB", "0 target.example param=value")
    assert data_svcb is not None
    assert data_svcb["svcPriority"] == 0
    assert data_svcb["svcTargetName"] == "target.example"


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

    # Test URL sanitization
    error = Exception("Request failed: https://api.example.com?password=secret123&token=abc123")
    result = sanitize_error_message(error)
    assert "password=secret123" not in result
    assert "token=abc123" not in result
    assert "password=***" in result or "***" in result
    assert "token=***" in result or "***" in result

    error = Exception("Auth failed: http://example.com/auth?api_key=12345&secret=mysecret")
    result = sanitize_error_message(error)
    assert "api_key=12345" not in result
    assert "secret=mysecret" not in result


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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
    data = json.loads(body_bytes)
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
    body_bytes = await collect_streaming_response(response)
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
    assert "Failed to create record" in str(exc_info.value.detail)
    mock_add.assert_called_once()


@pytest.mark.asyncio
async def test_apply_record_delete_exception_extra(
    app_state: AppState, mocker: MockerFixture
) -> None:
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
    mocker.patch.object(
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
