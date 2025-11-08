"""Technitium DNS API client."""

import logging
import ssl
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel

from .models import (
    AddRecordResponse,
    CreateZoneResponse,
    DeleteRecordResponse,
    GetRecordsResponse,
    GetZoneOptionsResponse,
    ListCatalogZonesResponse,
    ListZonesResponse,
    LoginResponse,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TechnitiumError(Exception):
    """Base exception for Technitium API errors."""

    def __init__(
        self,
        message: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
        inner_error: str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Error message
            error_message: API error message
            stack_trace: Stack trace from API
            inner_error: Inner error message from API
        """
        self.message = message
        self.error_message = error_message
        self.stack_trace = stack_trace
        self.inner_error = inner_error
        super().__init__(message)

    def __str__(self) -> str:
        """String representation of the error."""
        parts = [self.message]
        if self.error_message and self.error_message != self.message:
            parts.append(f"API Error: {self.error_message}")
        if self.inner_error:
            parts.append(f"Inner Error: {self.inner_error}")
        return " | ".join(parts)


class InvalidTokenError(TechnitiumError):
    """Exception raised when the API token is invalid or expired."""

    pass


class TechnitiumClient:
    """Client for interacting with Technitium DNS API."""

    ENDPOINT_LOGIN = "/api/user/login"
    ENDPOINT_CREATE_ZONE = "/api/zones/create"
    ENDPOINT_LIST_ZONES = "/api/zones/list"
    ENDPOINT_ADD_RECORD = "/api/zones/records/add"
    ENDPOINT_GET_RECORDS = "/api/zones/records/get"
    ENDPOINT_DELETE_RECORD = "/api/zones/records/delete"
    ENDPOINT_LIST_CATALOG_ZONES = "/api/zones/catalogs/list"
    ENDPOINT_GET_ZONE_OPTIONS = "/api/zones/options/get"
    ENDPOINT_SET_ZONE_OPTIONS = "/api/zones/options/set"
    ENDPOINT_ENROLL_CATALOG = "/api/zones/catalog/enroll"

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 10.0,
        verify_ssl: bool = True,
        ca_bundle: str | None = None,
    ) -> None:
        """Initialize the Technitium client.

        Args:
            base_url: Base URL of the Technitium DNS server
            token: Authentication token (optional, can be set later)
            timeout: Request timeout in seconds
            verify_ssl: Verify SSL certificates
            ca_bundle: Optional path to a PEM file with CA certificates
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.ca_bundle = ca_bundle

        # Configure TLS verification
        verify: Any = verify_ssl
        if not verify_ssl:
            # When verify_ssl is False, we need to create an SSL context that doesn't verify
            # and is permissive about TLS versions and ciphers
            logger.debug("SSL verification disabled - creating permissive unverified SSL context")
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                # Allow TLS 1.2+ for compatibility with self-signed certs
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                # Don't restrict cipher suites - allows compatibility with various server configs
                # Intentional: SECLEVEL=0 allows compatibility with self-signed/legacy servers
                # Only used when TECHNITIUM_VERIFY_SSL=false, which should only be for dev/testing
                # nosemgrep: python.lang.security.audit.insecure-transport.ssl.no-set-ciphers.no-set-ciphers
                context.set_ciphers("DEFAULT:@SECLEVEL=0")
                verify = context
                logger.debug("Created permissive SSL context for unverified connections")
            except Exception as e:
                logger.warning(
                    f"Failed to create unverified SSL context: {e}, falling back to verify=False"
                )
                verify = False
        elif ca_bundle:
            # Use ssl.create_default_context to load the CA bundle
            logger.debug(f"Using custom CA bundle: {ca_bundle}")
            verify = ssl.create_default_context(cafile=ca_bundle)
        else:
            logger.debug("Using system CA certificates for SSL verification")

        logger.debug(f"Creating httpx.AsyncClient with verify={verify}")
        self._client = httpx.AsyncClient(timeout=timeout, verify=verify)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TechnitiumClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _post_raw(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make a POST request to the API.

        Args:
            endpoint: API endpoint path
            data: Form data to send

        Returns:
            Response data

        Raises:
            TechnitiumError: If the request fails
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Sending POST request to {url}")

        try:
            response = await self._client.post(url, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TechnitiumError(
                f"Server responded with status code {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise TechnitiumError(f"Request error: {e}") from e

        try:
            parsed = response.json()
        except Exception as e:
            raise TechnitiumError(f"Failed to parse JSON response: {e}") from e

        if not isinstance(parsed, dict):
            raise TechnitiumError("Unexpected response format")

        result = cast(dict[str, Any], parsed)

        status = result.get("status")
        if status == "error":
            error_msg = result.get("errorMessage", "Unknown server error")
            stack_trace = result.get("stackTrace")
            inner_error = result.get("innerErrorMessage")
            raise TechnitiumError(
                f"API error: {error_msg}",
                error_message=error_msg,
                stack_trace=stack_trace,
                inner_error=inner_error,
            )
        elif status == "invalid-token":
            raise InvalidTokenError("Invalid or expired token")
        elif status != "ok":
            raise TechnitiumError(f"Unexpected response status: {status}")

        return result

    async def _post(self, endpoint: str, payload: dict[str, Any], response_model: type[T]) -> T:
        """Make an authenticated POST request.

        Args:
            endpoint: API endpoint path
            payload: Request payload
            response_model: Pydantic model for the response

        Returns:
            Parsed response object
        """
        data = {"token": self.token, **payload}
        result = await self._post_raw(endpoint, data)
        response_payload = result.get("response")

        if response_payload is None:
            response_payload = {}
        elif not isinstance(response_payload, dict):
            raise TechnitiumError("Unexpected response payload format")

        return response_model.model_validate(response_payload)

    async def login(self, username: str, password: str) -> LoginResponse:
        """Login to Technitium DNS.

        Args:
            username: Username
            password: Password

        Returns:
            Login response with token
        """
        data = {"user": username, "pass": password}
        result = await self._post_raw(self.ENDPOINT_LOGIN, data)
        return LoginResponse.model_validate(result)

    async def create_zone(
        self,
        zone: str,
        zone_type: str = "Forwarder",
        protocol: str | None = "Udp",
        forwarder: str | None = "this-server",
        dnssec_validation: bool | None = True,
        catalog: str | None = None,
        **extra_options: Any,
    ) -> CreateZoneResponse:
        """Create a new DNS zone.

        Args:
            zone: Zone name
            zone_type: Type of zone (Primary, Forwarder, etc.)
            protocol: Protocol to use (Udp, Tcp, etc.)
            forwarder: Forwarder address
            dnssec_validation: Enable DNSSEC validation

        Returns:
            Create zone response
        """
        payload: dict[str, Any] = {
            "zone": zone,
            "type": zone_type,
        }
        if protocol:
            payload["protocol"] = protocol
        if forwarder:
            payload["forwarder"] = forwarder
        if dnssec_validation is not None:
            payload["dnssecValidation"] = str(dnssec_validation).lower()
        if catalog:
            payload["catalog"] = catalog

        for key, value in extra_options.items():
            if value is None:
                continue
            if isinstance(value, bool):
                payload[key] = str(value).lower()
            else:
                payload[key] = value

        return await self._post(self.ENDPOINT_CREATE_ZONE, payload, CreateZoneResponse)

    async def list_zones(
        self,
        zone: str,
        page_number: int | None = None,
        zones_per_page: int | None = None,
    ) -> ListZonesResponse:
        """List DNS zones.

        Args:
            zone: Zone name pattern
            page_number: Page number
            zones_per_page: Zones per page

        Returns:
            List of zones
        """
        payload: dict[str, Any] = {"zone": zone}
        if page_number is not None:
            payload["pageNumber"] = page_number
        if zones_per_page is not None:
            payload["zonesPerPage"] = zones_per_page

        return await self._post(self.ENDPOINT_LIST_ZONES, payload, ListZonesResponse)

    async def add_record(
        self,
        domain: str,
        record_type: str,
        record_data: dict[str, Any],
        ttl: int | None = None,
        zone: str | None = None,
        comments: str | None = None,
        expiry_ttl: int | None = None,
        disabled: bool = False,
        overwrite: bool = False,
        ptr: bool = False,
        create_ptr_zone: bool = False,
        update_svcb_hints: bool = False,
    ) -> AddRecordResponse:
        """Add a DNS record.

        Args:
            domain: Domain name
            record_type: Record type (A, AAAA, CNAME, TXT, ANAME, CAA, URI, SSHFP, SVCB, HTTPS)
            record_data: Record data
            ttl: TTL in seconds
            zone: Zone name
            comments: Comments for the record
            expiry_ttl: Auto-delete record after this many seconds since last modification
            disabled: Create the record in disabled state
            overwrite: Overwrite existing records of this type
            ptr: Auto-create reverse PTR record (for A/AAAA records)
            create_ptr_zone: Auto-create reverse zone if needed
            update_svcb_hints: Update SVCB/HTTPS hints (for A/AAAA records)

        Returns:
            Add record response
        """
        payload: dict[str, Any] = {
            "domain": domain,
            "type": record_type,
            **record_data,
        }
        if ttl is not None:
            payload["ttl"] = ttl
        if zone:
            payload["zone"] = zone
        if comments:
            payload["comments"] = comments
        if expiry_ttl is not None:
            payload["expiryTtl"] = expiry_ttl
        if disabled:
            payload["disable"] = str(disabled).lower()
        if overwrite:
            payload["overwrite"] = str(overwrite).lower()
        if ptr:
            payload["ptr"] = str(ptr).lower()
        if create_ptr_zone:
            payload["createPtrZone"] = str(create_ptr_zone).lower()
        if update_svcb_hints:
            payload["updateSvcbHints"] = str(update_svcb_hints).lower()

        return await self._post(self.ENDPOINT_ADD_RECORD, payload, AddRecordResponse)

    async def get_records(
        self,
        domain: str,
        zone: str | None = None,
        list_zone: bool | None = None,
    ) -> GetRecordsResponse:
        """Get DNS records.

        Args:
            domain: Domain name
            zone: Zone name
            list_zone: List all zone records

        Returns:
            Get records response
        """
        payload: dict[str, Any] = {"domain": domain}
        if zone:
            payload["zone"] = zone
        if list_zone is not None:
            payload["listZone"] = str(list_zone).lower()

        return await self._post(self.ENDPOINT_GET_RECORDS, payload, GetRecordsResponse)

    async def delete_record(
        self,
        domain: str,
        record_type: str,
        record_data: dict[str, Any],
        zone: str | None = None,
    ) -> DeleteRecordResponse:
        """Delete a DNS record.

        Args:
            domain: Domain name
            record_type: Record type
            record_data: Record data
            zone: Zone name

        Returns:
            Delete record response
        """
        payload: dict[str, Any] = {
            "domain": domain,
            "type": record_type,
            **record_data,
        }
        if zone:
            payload["zone"] = zone

        return await self._post(self.ENDPOINT_DELETE_RECORD, payload, DeleteRecordResponse)

    async def list_catalog_zones(self) -> ListCatalogZonesResponse:
        """List available catalog zones on the server."""

        payload: dict[str, Any] = {}
        return await self._post(
            self.ENDPOINT_LIST_CATALOG_ZONES,
            payload,
            ListCatalogZonesResponse,
        )

    async def get_zone_options(
        self, zone: str, include_catalog_names: bool = False
    ) -> GetZoneOptionsResponse:
        """Retrieve zone options for the specified zone."""

        payload: dict[str, Any] = {"zone": zone}
        if include_catalog_names:
            payload["includeAvailableCatalogZoneNames"] = "true"

        return await self._post(
            self.ENDPOINT_GET_ZONE_OPTIONS,
            payload,
            GetZoneOptionsResponse,
        )

    async def set_zone_options(self, zone: str, **options: Any) -> None:
        """Set zone options for the specified zone."""

        payload: dict[str, Any] = {"zone": zone}
        for key, value in options.items():
            if value is None:
                continue
            if isinstance(value, bool):
                payload[key] = str(value).lower()
            elif isinstance(value, list):
                payload[key] = ",".join(value)
            else:
                payload[key] = value

        await self._post_raw(self.ENDPOINT_SET_ZONE_OPTIONS, payload)

    async def enroll_catalog(self, member_zone: str, catalog_zone: str) -> None:
        """Enroll a zone in a catalog zone.

        Args:
            member_zone: Zone name to enroll
            catalog_zone: Catalog zone name
        """
        payload: dict[str, Any] = {"zone": member_zone, "catalogZone": catalog_zone}
        await self._post_raw(self.ENDPOINT_ENROLL_CATALOG, payload)
