"""Tests for standard DNS record type translation."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.app_state import AppState
from external_dns_technitium_webhook.config import Config
from external_dns_technitium_webhook.handlers import (
    SUPPORTED_RECORD_TYPES,
    _extract_targets,
    _get_record_data,
    _record_stream,
)
from external_dns_technitium_webhook.models import (
    Changes,
    Endpoint,
    GetRecordsResponse,
    RecordInfo,
    ZoneInfo,
)


@pytest.fixture
def app_state(mocker: MockerFixture) -> AppState:
    state = AppState(
        Config(
            technitium_url="https://localhost:5380",
            technitium_username="admin",
            technitium_password="admin",
            zone="example.com",
        )
    )
    state.is_ready = True
    state.is_writable = True
    mocker.patch.object(state.client, "add_record", new=AsyncMock())
    mocker.patch.object(state.client, "delete_record", new=AsyncMock())
    return state


def test_standard_record_types_are_whitelisted() -> None:
    """All record types handled by the generic CRUD path are streamed."""
    assert {"DNAME", "SRV", "NS", "PTR", "MX", "NAPTR", "TLSA"}.issubset(SUPPORTED_RECORD_TYPES)


@pytest.mark.asyncio
async def test_stream_serializes_new_record_types() -> None:
    records = [
        ("NS", {"nameServer": "ns1.example.com"}, "ns1.example.com"),
        ("PTR", {"ptrName": "host.example.com"}, "host.example.com"),
        ("MX", {"preference": 10, "exchange": "mail.example.com"}, "10 mail.example.com"),
        ("SRV", {"priority": 1, "weight": 2, "port": 443, "target": "."}, "1 2 443 ."),
        (
            "NAPTR",
            {
                "order": 100,
                "preference": 10,
                "flags": "U",
                "services": "E2U+sip",
                "regexp": "!^.*$!sip:info@example.com!",
                "replacement": ".",
            },
            '100 10 "U" "E2U+sip" "!^.*$!sip:info@example.com!" .',
        ),
        ("DNAME", {"dname": "target.example.net"}, "target.example.net"),
        (
            "TLSA",
            {
                "certificateUsage": "DANE-EE",
                "selector": "SPKI",
                "matchingType": "SHA2-256",
                "certificateAssociationData": "0123ABCD",
            },
            "3 1 1 0123ABCD",
        ),
    ]
    response = GetRecordsResponse(
        zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
        records=[
            RecordInfo(
                disabled=False,
                name=f"record-{index}.example.com",
                type=record_type,
                ttl=300,
                rData=r_data,
            )
            for index, (record_type, r_data, _target) in enumerate(records)
        ],
    )
    chunks: list[str] = []
    async for chunk in _record_stream(response):
        chunks.append(chunk)

    endpoints = json.loads("".join(chunks))
    assert [endpoint["targets"][0] for endpoint in endpoints] == [
        target for _, _, target in records
    ]


@pytest.mark.parametrize(
    ("record_type", "target", "expected"),
    [
        ("NS", "ns1.example.com.", {"nameServer": "ns1.example.com."}),
        ("PTR", ".", {"ptrName": "."}),
        ("MX", "10 mail.example.com.", {"preference": 10, "exchange": "mail.example.com."}),
        (
            "SRV",
            "0 0 443 .",
            {"priority": 0, "weight": 0, "port": 443, "target": "."},
        ),
        (
            "NAPTR",
            '100 10 "U" "E2U+sip" "!^.*$!sip:\\1@example.com!" .',
            {
                "naptrOrder": 100,
                "naptrPreference": 10,
                "naptrFlags": "U",
                "naptrServices": "E2U+sip",
                "naptrRegexp": "!^.*$!sip:\\1@example.com!",
                "naptrReplacement": ".",
            },
        ),
        ("DNAME", "target.example.net.", {"dname": "target.example.net."}),
        (
            "TLSA",
            "3 1 1 0123abcd",
            {
                "tlsaCertificateUsage": "DANE-EE",
                "tlsaSelector": "SPKI",
                "tlsaMatchingType": "SHA2-256",
                "tlsaCertificateAssociationData": "0123abcd",
            },
        ),
    ],
)
def test_parse_external_dns_target(record_type: str, target: str, expected: dict[str, Any]) -> None:
    assert _get_record_data(record_type, target) == expected


@pytest.mark.parametrize(
    ("record_type", "target"),
    [
        ("MX", "70000 mail.example.com"),
        ("SRV", "0 0 65536 target.example.com"),
        ("NAPTR", '1 2 "U" "S" "unterminated .'),
        ("TLSA", "3 1 1 abc"),  # odd number of hex digits
        ("TLSA", "3 4 1 0011"),
    ],
)
def test_parse_external_dns_target_rejects_invalid_data(record_type: str, target: str) -> None:
    assert _get_record_data(record_type, target) is None


def test_extract_targets_accepts_record_like_values() -> None:
    record = SimpleNamespace(
        type="TLSA",
        r_data={
            "certificateUsage": "PKIX-EE",
            "selector": "Cert",
            "matchingType": "Full",
            "certificateAssociationData": "AABB",
        },
    )
    assert _extract_targets(record) == ["1 0 0 AABB"]


@pytest.mark.asyncio
async def test_apply_record_create_and_delete_new_types(app_state, mocker: MockerFixture) -> None:
    """Generic CRUD processing sends Technitium's field names for new types."""
    add = mocker.patch.object(app_state.client, "add_record")
    delete = mocker.patch.object(app_state.client, "delete_record")
    endpoint = Endpoint(
        dnsName="_443._tcp.example.com",
        recordType="SRV",
        recordTTL=300,
        setIdentifier="",
        targets=["0 5 443 ."],
    )
    tlsa = Endpoint(
        dnsName="_443._tcp.example.com",
        recordType="TLSA",
        recordTTL=300,
        setIdentifier="",
        targets=["3 1 1 0123ABCD"],
    )

    from external_dns_technitium_webhook.handlers import apply_record

    response = await apply_record(
        app_state,
        Changes(
            create=[endpoint, tlsa],
            updateOld=None,
            updateNew=None,
            delete=[endpoint, tlsa],
        ),
    )
    assert response.status_code == 204
    assert add.call_args_list[0].kwargs["record_data"] == {
        "priority": 0,
        "weight": 5,
        "port": 443,
        "target": ".",
    }
    assert add.call_args_list[1].kwargs["record_data"]["tlsaCertificateUsage"] == "DANE-EE"
    assert delete.call_args_list[0].kwargs["record_data"]["target"] == "."
    assert delete.call_args_list[1].kwargs["record_data"]["tlsaMatchingType"] == "SHA2-256"
