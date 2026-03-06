"""Technitium DNS API client."""

import gzip
import logging
import ssl
import time
from typing import Any, Self, cast
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from .metrics import api_errors_total, technitium_latency_seconds
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
from .resilience import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class _LatencyTracker:
    """Async context manager to track latency of an operation."""

    def __init__(self, operation: str) -> None:
        """Initialize the latency tracker.

        Args:
            operation: Operation name label for the metric
        """
        self.operation = operation
        self._timer = technitium_latency_seconds.labels(operation=operation).time()

    async def __aenter__(self) -> None:
        """Async context manager entry."""
        self._timer.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        self._timer.__exit__(exc_type, exc_val, exc_tb)


def _track_latency(operation: str) -> _LatencyTracker:
    """Create a context manager to track latency of an operation.

    Args:
        operation: Operation name label for the metric

    Returns:
        Async context manager for tracking latency
    """
    return _LatencyTracker(operation)


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
        enable_request_compression: bool = False,
        compression_threshold_bytes: int = 32768,
        circuit_breaker: CircuitBreaker | None = None,
        records_cache_ttl_seconds: float = 0.0,
    ) -> None:
        """Initialize the Technitium client.

        Args:
            base_url: Base URL of the Technitium DNS server
            token: Authentication token (optional, can be set later)
            timeout: Request timeout in seconds
            verify_ssl: Verify SSL certificates
            ca_bundle: Optional path to a PEM file with CA certificates
            enable_request_compression: Enable gzip compression for large request bodies
            compression_threshold_bytes: Minimum size for request compression
            circuit_breaker: Optional circuit breaker for protecting API calls
            records_cache_ttl_seconds: TTL for get_records cache entries (0 to disable)
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.ca_bundle = ca_bundle
        self.enable_request_compression = enable_request_compression
        self.compression_threshold_bytes = compression_threshold_bytes
        self.circuit_breaker = circuit_breaker

        # Configure TLS verification.  The default behavior is to let httpx
        # perform full certificate and hostname validation using the system
        # CA store (or a custom bundle if one is specified).  For unit and
        # integration tests we support an override via ``verify_ssl=False``
        # which simply passes ``verify=False`` to httpx.  This disables all
        # TLS checks and should never be enabled in production; keeping the
        # override branch minimal ensures static analyzers do not complain.
        verify: Any = verify_ssl
        if not verify_ssl:
            logger.warning("SSL verification disabled; connections will be insecure")
            verify = False
        elif ca_bundle:
            # Use ssl.create_default_context to load the CA bundle
            logger.debug(f"Using custom CA bundle: {ca_bundle}")
            verify = ssl.create_default_context(cafile=ca_bundle)
        else:
            logger.debug("Using system CA certificates for SSL verification")

        logger.debug(f"Creating httpx.AsyncClient with verify={verify}")
        # store the final value for testing/inspection; httpx may wrap SSL
        # contexts internally and is harder to introspect later.
        self._verify = verify
        self._client = httpx.AsyncClient(timeout=timeout, verify=verify)
        self._records_cache_ttl_seconds = records_cache_ttl_seconds
        self._records_cache: dict[
            tuple[str, str | None, bool | None], tuple[float, GetRecordsResponse]
        ] = {}

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def _invalidate_records_cache(self) -> None:
        """Invalidate cached get_records responses."""
        self._records_cache.clear()

    async def _post_raw(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make a POST request to the API.

        See :func:`_parse_response` for the logic that validates and unwraps the
        response payload.  This helper exists primarily to keep
        ``_post_raw`` below the cognitive complexity threshold required by
        SonarCloud.

        Args:
            endpoint: API endpoint path
            data: Form data to send

        Raises:
            TechnitiumError: If the request fails
            CircuitBreakerOpenError: If the circuit breaker is open
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Sending POST request to {url}")

        form_encoded = urlencode(data)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async def _do_request() -> Any:
            if self.enable_request_compression:
                raw_bytes = form_encoded.encode("utf-8")
                if len(raw_bytes) >= self.compression_threshold_bytes:
                    content = gzip.compress(raw_bytes)
                    headers["Content-Encoding"] = "gzip"
                    logger.debug(
                        f"Compressed request payload from {len(raw_bytes)} to {len(content)} bytes"
                    )
                    return await self._client.post(url, content=content, headers=headers)
            return await self._client.post(url, data=data, headers=headers)

        try:
            if self.circuit_breaker is not None:
                response = await self.circuit_breaker.call(_do_request())
            else:
                response = await _do_request()
            response.raise_for_status()
        except CircuitBreakerOpenError:
            api_errors_total.labels(error_type="circuit_open").inc()
            raise
        except httpx.TimeoutException as e:
            api_errors_total.labels(error_type="timeout").inc()
            # Include exception type name if the message is empty
            error_msg = str(e) if str(e) else type(e).__name__
            raise TechnitiumError(f"Request error: {error_msg}") from e
        except httpx.HTTPStatusError as e:
            raise TechnitiumError(
                f"Server responded with status code {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            api_errors_total.labels(error_type="connection_error").inc()
            # Include exception type name if the message is empty
            error_msg = str(e) if str(e) else type(e).__name__
            raise TechnitiumError(f"Request error: {error_msg}") from e

        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Validate and extract JSON data from a Technitium API response.

        This method is factored out of ``_post_raw`` to reduce its cognitive
        complexity.  It performs the following steps:

        1. Parse JSON and ensure it is a dict.
        2. Inspect the ``status`` field and raise the appropriate
           ``TechnitiumError`` subclass if anything is amiss.
        """
        try:
            parsed = response.json()
        except Exception as e:
            # A malformed response is unexpected but should result in an
            # explicit error.  We exercise this path in unit tests to ensure
            # the exception message is sensible and that coverage tools count
            # it.
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
        if status == "invalid-token":
            api_errors_total.labels(error_type="invalid_token").inc()
            raise InvalidTokenError("Invalid or expired token")
        if status != "ok":
            raise TechnitiumError(f"Unexpected response status: {status}")

        return result

    async def _post[T: BaseModel](
        self,
        endpoint: str,
        payload: dict[str, Any],
        response_model: type[T],
    ) -> T:
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
        async with _track_latency("login"):
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

        async with _track_latency("add_record"):
            response = await self._post(self.ENDPOINT_ADD_RECORD, payload, AddRecordResponse)
        self._invalidate_records_cache()
        return response

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

        if self._records_cache_ttl_seconds > 0:
            cache_key = (domain, zone, list_zone)
            cached = self._records_cache.get(cache_key)
            now = time.monotonic()
            if cached and now - cached[0] < self._records_cache_ttl_seconds:
                return cached[1]

        async with _track_latency("get_records"):
            response = await self._post(self.ENDPOINT_GET_RECORDS, payload, GetRecordsResponse)

        if self._records_cache_ttl_seconds > 0:
            self._records_cache[(domain, zone, list_zone)] = (time.monotonic(), response)

        return response

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

        self._invalidate_records_cache()
        async with _track_latency("delete_record"):
            response = await self._post(self.ENDPOINT_DELETE_RECORD, payload, DeleteRecordResponse)
        return response

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

        data = {"token": self.token, **payload}
        await self._post_raw(self.ENDPOINT_SET_ZONE_OPTIONS, data)

    async def enroll_catalog(self, member_zone: str, catalog_zone: str) -> None:
        """Enroll a zone in a catalog zone.

        Args:
            member_zone: Zone name to enroll
            catalog_zone: Catalog zone name
        """
        payload: dict[str, Any] = {"zone": member_zone, "catalogZone": catalog_zone}
        data = {"token": self.token, **payload}
        await self._post_raw(self.ENDPOINT_ENROLL_CATALOG, data)
