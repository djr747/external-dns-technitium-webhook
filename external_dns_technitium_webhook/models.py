"""Data models for ExternalDNS webhook API."""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class ProviderSpecificProperty(BaseModel):
    """Provider-specific property in an endpoint."""

    name: str
    value: str


class Endpoint(BaseModel):
    """DNS endpoint representing a DNS record."""

    dns_name: str = Field(..., alias="dnsName")
    targets: list[str] = Field(default_factory=list)
    record_type: str = Field(..., alias="recordType")
    record_ttl: int | None = Field(None, alias="recordTTL", ge=0, le=2147483647)
    set_identifier: str = Field("", alias="setIdentifier")
    labels: dict[str, str] = Field(default_factory=dict)
    provider_specific: list[ProviderSpecificProperty] = Field(
        default_factory=list, alias="providerSpecific"
    )

    model_config = {"populate_by_name": True}

    @field_validator("dns_name")
    @classmethod
    def validate_dns_name(cls, v: str) -> str:
        """Validate DNS name format (RFC 1035/1123), allowing leading underscores.

        Args:
            v: DNS name to validate

        Returns:
            Validated DNS name

        Raises:
            ValueError: If DNS name is invalid
        """
        if not v:
            raise ValueError("DNS name cannot be empty")

        if len(v) > 253:
            raise ValueError("DNS name exceeds maximum length of 253 characters")

        # Allow leading underscores for service records (e.g., _https._tcp)
        # and wildcard records (*.example.com)
        normalized_v = v
        if normalized_v.startswith("*."):
            normalized_v = normalized_v[2:]

        # Each label must be between 1 and 63 characters long
        labels = normalized_v.split(".")
        if not all(1 <= len(label) <= 63 for label in labels if label):
            raise ValueError("Invalid label length in DNS name")

        # Regex for valid hostname characters (alphanumeric, hyphen, underscore)
        # allowing leading underscore.
        label_regex = re.compile(r"^(?!-)[a-zA-Z0-9_-]{1,63}(?<!-)$")
        if not all(label_regex.match(label) for label in labels if label):
            raise ValueError("Invalid characters in DNS name label")

        return v

    @field_validator("record_ttl")
    @classmethod
    def validate_ttl(cls, v: int | None) -> int | None:
        """Validate TTL is in reasonable range.

        Args:
            v: TTL value to validate

        Returns:
            Validated TTL value
        """
        if v is not None and v > 86400:
            # Warn about very high TTL values (> 24 hours)
            logger.warning(f"Unusually high TTL value: {v} seconds (> 24 hours)")

        return v


class Changes(BaseModel):
    """DNS record changes to be applied."""

    create: list[Endpoint] | None = None
    update_old: list[Endpoint] | None = Field(None, alias="updateOld")
    update_new: list[Endpoint] | None = Field(None, alias="updateNew")
    delete: list[Endpoint] | None = None

    model_config = {"populate_by_name": True}


class DomainFilter(BaseModel):
    """Domain filter configuration."""

    filters: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class RecordAData(BaseModel):
    """A record data."""

    ip_address: str = Field(..., alias="ipAddress")


class RecordAAAAData(BaseModel):
    """AAAA record data."""

    ip_address: str = Field(..., alias="ipAddress")


class RecordCNAMEData(BaseModel):
    """CNAME record data."""

    cname: str


class RecordTXTData(BaseModel):
    """TXT record data."""

    text: str


class RecordANAMEData(BaseModel):
    """ANAME record data (Technitium proprietary)."""

    aname: str


class RecordCAAData(BaseModel):
    """CAA record data."""

    flags: int
    tag: str
    value: str


class RecordURIData(BaseModel):
    """URI record data."""

    priority: int = Field(..., alias="uriPriority")
    weight: int = Field(..., alias="uriWeight")
    uri: str

    model_config = {"populate_by_name": True}


class RecordSSHFPData(BaseModel):
    """SSHFP record data."""

    algorithm: int
    fingerprint_type: int = Field(..., alias="fingerprintType")
    fingerprint: str

    model_config = {"populate_by_name": True}


class RecordSVCBData(BaseModel):
    """SVCB/HTTPS record data."""

    priority: int = Field(..., alias="svcPriority")
    target_name: str = Field(..., alias="svcTargetName")
    svc_params: str | None = Field(None, alias="svcParams")
    auto_ipv4_hint: bool = Field(False, alias="autoIpv4Hint")
    auto_ipv6_hint: bool = Field(False, alias="autoIpv6Hint")

    model_config = {"populate_by_name": True}


class RecordInfo(BaseModel):
    """DNS record information from Technitium."""

    disabled: bool
    name: str
    ttl: int
    type: str
    r_data: dict[str, Any] = Field(..., alias="rData")

    model_config = {"populate_by_name": True}


class ZoneInfo(BaseModel):
    """Zone information from Technitium."""

    name: str
    type: str
    internal: bool | None = None
    disabled: bool


class GetRecordsResponse(BaseModel):
    """Response from get records API."""

    zone: ZoneInfo
    records: list[RecordInfo]


class AddRecordResponse(BaseModel):
    """Response from add record API."""

    zone: ZoneInfo
    added_record: RecordInfo = Field(..., alias="addedRecord")

    model_config = {"populate_by_name": True}


class DeleteRecordResponse(BaseModel):
    """Response from delete record API."""

    pass


class LoginResponse(BaseModel):
    """Response from login API."""

    display_name: str = Field(..., alias="displayName")
    username: str
    token: str

    model_config = {"populate_by_name": True}


class CreateZoneResponse(BaseModel):
    """Response from create zone API."""

    domain: str


class ListZonesResponse(BaseModel):
    """Response from list zones API."""

    page_number: int = Field(..., alias="pageNumber")
    total_pages: int = Field(..., alias="totalPages")
    total_zones: int = Field(..., alias="totalZones")
    zones: list[ZoneInfo]

    model_config = {"populate_by_name": True}


class ListCatalogZonesResponse(BaseModel):
    """Response from list catalog zones API."""

    catalog_zones: list[str] = Field(default_factory=list, alias="catalogZones")

    model_config = {"populate_by_name": True}


class GetZoneOptionsResponse(BaseModel):
    """Response from get zone options API."""

    zone: str
    is_catalog_zone: bool = Field(False, alias="isCatalogZone")
    is_read_only: bool = Field(False, alias="isReadOnly")
    catalog_zone_name: str | None = Field(None, alias="catalogZoneName")
    available_catalog_zone_names: list[str] = Field(
        default_factory=list, alias="availableCatalogZoneNames"
    )

    model_config = {"populate_by_name": True}
