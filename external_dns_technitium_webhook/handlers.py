"""API handlers for ExternalDNS webhook endpoints."""

import ipaddress
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable
from contextlib import suppress
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import Response, StreamingResponse

from external_dns_technitium_webhook.models import GetRecordsResponse

from .app_state import AppState
from .logging_utils import safe_log_payload
from .metrics import api_errors_total, dns_records_processed_total, dns_records_total, webhook_ready
from .models import Changes, DomainFilter, Endpoint
from .resilience import CircuitBreakerOpenError, CircuitState
from .responses import ExternalDNSResponse
from .technitium_client import TechnitiumError

logger = logging.getLogger(__name__)

# Record types understood by both the read and write paths.  Keeping this as
# one whitelist avoids exposing records that the webhook cannot round-trip.
SUPPORTED_RECORD_TYPES = (
    "A",
    "AAAA",
    "NS",
    "CNAME",
    "PTR",
    "MX",
    "TXT",
    "SRV",
    "NAPTR",
    "DNAME",
    "TLSA",
    "ANAME",
    "CAA",
    "URI",
    "SSHFP",
    "SVCB",
    "HTTPS",
)


def _quote_rdata_text(value: Any) -> str:
    """Quote a character-string field in DNS presentation format."""
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def _domain_rdata_target(value: Any) -> str:
    """Render Technitium's empty internal root name in presentation format."""
    return "." if value is None or value == "" else str(value)


def _sshfp_algorithm_to_number(value: Any) -> str:
    """Render Technitium's SSHFP algorithm name in DNS presentation format."""
    mapping = {"RSA": "1", "DSA": "2", "ECDSA": "3", "ED25519": "4", "ED448": "6"}
    normalized = str(value).upper()
    return mapping.get(normalized, str(value))


def _sshfp_fingerprint_type_to_number(value: Any) -> str:
    """Render Technitium's SSHFP fingerprint type in DNS presentation format."""
    mapping = {"SHA1": "1", "SHA256": "2"}
    normalized = str(value).replace("-", "").upper()
    return mapping.get(normalized, str(value))


def _svc_params_to_target(value: Any) -> str:
    """Render Technitium's SvcParam object in ExternalDNS target syntax."""
    if isinstance(value, dict):
        return " ".join(f"{key}={param_value}" for key, param_value in value.items())
    return str(value) if value else ""


def _is_connection_error(error: Exception) -> bool:
    """Check if an error is a connection/network-level error.

    These kinds of errors warrant an attempt to failover to alternate endpoints.

    Args:
        error: Exception to check

    Returns:
        True if error appears to be a connection/network-level error
    """
    if not isinstance(error, TechnitiumError):
        return False

    error_str = str(error).lower()

    # If error message is just "request error:" with nothing meaningful after it,
    # this is likely a connection timeout or similar network-level error.
    # These occur when httpx exceptions have minimial string representations.
    if error_str.strip() in ("request error:", "request error: "):
        return True

    # Check for common connection/network error patterns
    connection_patterns = [
        "connection refused",
        "connection reset",
        "connection timeout",  # Pattern in message text
        "connecttimeout",  # Exception type name (lowercase)
        "connecterror",  # Exception type name (lowercase)
        "connection error",  # Generic connection error
        "temporary failure in name resolution",  # DNS failure
        "name or service not known",  # DNS failure
        "nodename nor servname provided",  # DNS/lookup failure
        "cannot assign requested address",
        "network is unreachable",
        "host is unreachable",
        "connection aborted",
        "no route to host",
        "all connection attempts failed",  # Generic httpx error
        "errno -3",  # Temporary failure in name resolution (numeric)
        "errno -2",  # Name or service not known (numeric)
        "errno -11",  # Temporary failure (numeric)
    ]

    return any(pattern in error_str for pattern in connection_patterns)


def sanitize_error_message(error: Exception) -> str:
    """Sanitize error message to prevent information disclosure.

    Removes sensitive patterns like passwords, tokens, file paths, etc.

    Args:
        error: Original exception

    Returns:
        Safe error message for client response
    """
    error_str = str(error)
    redaction_string = "***"

    def _replace_sensitive_param(match: re.Match[str]) -> str:
        """Replace sensitive parameter values with redaction string.

        The regex captures the parameter name in group(1), so we reconstruct
        the full pattern as 'param_name=***' to keep the param name visible
        while hiding the actual value.
        """
        param_name = match.group(1)
        # Determine separator (= or :) from the original match
        separator = "=" if "=" in match.group() else ":"
        return f"{param_name}{separator}{redaction_string}"

    # Remove sensitive patterns
    sensitive_patterns: list[tuple[str, str | Callable[[re.Match[str]], str]]] = [
        (r"password[=:]\s*\S+", f"password={redaction_string}"),
        (r"token[=:]\s*\S+", f"token={redaction_string}"),
        (r"api[_-]?key[=:]\s*\S+", f"api_key={redaction_string}"),
        (r"secret[=:]\s*\S+", f"secret={redaction_string}"),
        (r"auth[=:]\s*\S+", f"auth={redaction_string}"),
        (r"/home/[^/\s]+", f"/home/{redaction_string}"),
        (r"/Users/[^/\s]+", f"/Users/{redaction_string}"),
        (r"C:\\Users\\[^\\s]+", rf"C:\\Users\\{redaction_string}"),
        # Sanitize URLs with sensitive query parameters
        # This pattern captures the param name in group(1) and matches the value
        (
            r"(password|token|api[_-]?key|secret|auth)[=:][^\s&]+",
            _replace_sensitive_param,
        ),
    ]

    for pattern, replacement in sensitive_patterns:
        error_str = re.sub(pattern, replacement, error_str, flags=re.IGNORECASE)

    return error_str


def health_check(state: AppState) -> Response:
    """Health check endpoint.

    Args:
        state: Application state

    Returns:
        200 OK if ready, 503 if not ready or circuit breaker is open
    """
    cb = getattr(state, "circuit_breaker", None)
    circuit_open = cb is not None and cb.state == CircuitState.OPEN

    if not state.is_ready or circuit_open:
        webhook_ready.set(0)
        detail: dict[str, str] = {"status": "unhealthy"}
        if circuit_open:
            detail["circuit_breaker"] = "open"
        return ExternalDNSResponse(content=detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    webhook_ready.set(1)
    return ExternalDNSResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)


def negotiate_domain_filter(state: AppState) -> ExternalDNSResponse:
    """Negotiate domain filters with ExternalDNS.

    Args:
        state: Application state

    Returns:
        Domain filter configuration
    """
    state.ensure_ready()

    domain_filter = DomainFilter(
        filters=state.config.domain_filter_list,
        exclude=[],
    )

    logger.debug(f"Negotiated domain filters: {domain_filter.filters}")
    return ExternalDNSResponse(content=domain_filter.model_dump())


# constant used in multiple error responses
API_UNAVAILABLE = "Upstream Technitium API temporarily unavailable"


def _handle_circuit_error(cboe: CircuitBreakerOpenError) -> None:
    """Raise HTTPException for circuit breaker open errors."""
    retry_after = int(cboe.retry_after) if cboe.retry_after and cboe.retry_after > 0 else 0
    headers = {"Retry-After": str(retry_after)} if retry_after > 0 else None
    api_errors_total.labels(error_type="circuit_open").inc()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=API_UNAVAILABLE,
        headers=headers,
    ) from cboe


def _log_fetch_metrics(state: AppState, response: GetRecordsResponse, duration_ms: float) -> None:
    """Auxiliary logging/metrics after successful get_records call."""
    with suppress(Exception):
        state.record_fetch_count += 1
    with suppress(Exception):
        dns_records_total.set(len(response.records))
    logger.info(
        f"Successfully retrieved {len(response.records)} DNS record(s) for zone {state.config.zone} in {duration_ms:.1f}ms"
    )


def _extract_targets(record: Any) -> list[str]:
    """Compute the target list for a given record.

    Returns a list of strings suitable for the ``targets`` field of an
    ExternalDNS endpoint.  This logic was extracted from the original
    `get_records` handler to reduce its complexity.
    """
    r_type = record.type
    r_data = record.r_data

    if r_type in ("A", "AAAA"):
        return [r_data.get("ipAddress", "")]
    if r_type == "CNAME":
        return [r_data.get("cname", "")]
    if r_type == "NS":
        return [_domain_rdata_target(r_data.get("nameServer"))]
    if r_type == "PTR":
        return [_domain_rdata_target(r_data.get("ptrName"))]
    if r_type == "DNAME":
        return [_domain_rdata_target(r_data.get("dname"))]
    if r_type == "MX":
        exchange = _domain_rdata_target(r_data.get("exchange"))
        return [f"{r_data.get('preference', 0)} {exchange}"]
    if r_type == "TXT":
        return [r_data.get("text", "")]
    if r_type == "ANAME":
        return [r_data.get("aname", "")]
    if r_type == "CAA":
        flags = r_data.get("flags", 0)
        tag = r_data.get("tag", "")
        value = r_data.get("value", "")
        return [f'{flags} {tag} "{value}"']
    if r_type == "URI":
        priority = r_data.get("priority", 0)
        weight = r_data.get("weight", 0)
        uri = r_data.get("uri", "")
        return [f'{priority} {weight} "{uri}"']
    if r_type == "SSHFP":
        algorithm = _sshfp_algorithm_to_number(r_data.get("algorithm", 0))
        fp_type = _sshfp_fingerprint_type_to_number(r_data.get("fingerprintType", 0))
        fingerprint = r_data.get("fingerprint", "")
        return [f"{algorithm} {fp_type} {fingerprint}"]
    if r_type == "SRV":
        priority = r_data.get("priority", 0)
        weight = r_data.get("weight", 0)
        port = r_data.get("port", 0)
        target = _domain_rdata_target(r_data.get("target"))
        return [f"{priority} {weight} {port} {target}"]
    if r_type == "NAPTR":
        order = r_data.get("order", 0)
        preference = r_data.get("preference", 0)
        flags = _quote_rdata_text(r_data.get("flags", ""))
        services = _quote_rdata_text(r_data.get("services", ""))
        regexp = _quote_rdata_text(r_data.get("regexp", ""))
        replacement = _domain_rdata_target(r_data.get("replacement"))
        return [f"{order} {preference} {flags} {services} {regexp} {replacement}"]
    if r_type == "TLSA":
        usage = _tlsa_usage_to_number(r_data.get("certificateUsage", ""))
        selector = _tlsa_selector_to_number(r_data.get("selector", ""))
        matching_type = _tlsa_matching_type_to_number(r_data.get("matchingType", ""))
        association_data = r_data.get("certificateAssociationData", "")
        return [f"{usage} {selector} {matching_type} {association_data}"]
    if r_type in ("SVCB", "HTTPS"):
        priority = r_data.get("svcPriority", 0)
        target = _domain_rdata_target(r_data.get("svcTargetName"))
        params = _svc_params_to_target(r_data.get("svcParams", {}))
        return [f"{priority} {target} {params}".strip()]
    # fallback: wrap raw data
    return [r_data] if not isinstance(r_data, list) else r_data


async def _record_stream(response: GetRecordsResponse) -> AsyncGenerator[str]:
    """Yield JSON fragments for each valid record in the response."""
    yield "["
    first = True
    for record in response.records:
        if record.type not in SUPPORTED_RECORD_TYPES:
            continue

        endpoint = Endpoint(
            dnsName=record.name,
            recordType=record.type,
            recordTTL=record.ttl,
            setIdentifier="",
            targets=[],
        )
        endpoint.targets = _extract_targets(record)

        if not first:
            yield ","
        first = False
        yield json.dumps(endpoint.model_dump(by_alias=True))

    yield "]"


async def _handle_get_records_error(state: AppState, exc: TechnitiumError) -> GetRecordsResponse:
    """Handle errors during get_records with failover support.

    Args:
        state: Application state
        exc: Exception that occurred

    Returns:
        GetRecordsResponse on successful retry

    Raises:
        HTTPException: For various error conditions
    """
    if not _is_connection_error(exc):
        # Not a connection error, return error response
        logger.exception("API error during get_records: %s", exc)
        sanitized = sanitize_error_message(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sanitized,
        ) from exc

    # Connection error: attempt failover
    logger.warning(
        "Connection error detected, attempting failover to alternate endpoints: %s",
        exc,
    )
    failover_ok, is_writable = await state.try_failover_endpoints()

    if failover_ok:
        # Retry the operation with the new endpoint
        logger.info(
            "Failover successful to %s endpoint, retrying get_records",
            "writable" if is_writable else "read-only",
        )
        try:
            return await state.client.get_records(
                domain=state.config.zone,
                list_zone=True,
            )
        except Exception as retry_exc:
            logger.exception("Retry failed after failover: %s", retry_exc)
            await state.update_status(
                ready=False,
                writable=False,
                server_role=None,
                catalog_membership=None,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. All failover endpoints failed.",
            ) from retry_exc

    # Failover failed
    logger.error("Failover to alternate endpoints failed")
    await state.update_status(
        ready=False,
        writable=False,
        server_role=None,
        catalog_membership=None,
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable. Failed to reach any Technitium endpoint.",
    ) from exc


async def get_records(state: AppState) -> Response:
    """Get current DNS records and stream them to the caller."""
    state.ensure_ready()

    import time

    logger.debug("Fetching DNS records")
    start = time.monotonic()

    try:
        response = await state.client.get_records(
            domain=state.config.zone,
            list_zone=True,
        )
    except CircuitBreakerOpenError as cboe:
        _handle_circuit_error(cboe)
    except TechnitiumError as exc:
        response = await _handle_get_records_error(state, exc)

    duration_ms = (time.monotonic() - start) * 1000.0
    _log_fetch_metrics(state, response, duration_ms)

    return StreamingResponse(_record_stream(response), media_type=ExternalDNSResponse.media_type)


def adjust_endpoints(state: AppState, endpoints: list[Endpoint]) -> ExternalDNSResponse:
    """Adjust endpoints before applying changes.

    Args:
        state: Application state
        endpoints: Endpoints to adjust

    Returns:
        Adjusted endpoints (no changes in this implementation)
    """
    state.ensure_ready()

    # Log the incoming endpoints payload safely for diagnostics.
    try:
        safe_log_payload(
            "adjust_endpoints.endpoints", [ep.model_dump(by_alias=True) for ep in endpoints], logger
        )
    except Exception:
        logger.debug("Failed to log adjust_endpoints payload", exc_info=True)

    # We don't do any endpoint adjustment
    return ExternalDNSResponse(content=[ep.model_dump(by_alias=True) for ep in endpoints])


async def _handle_apply_record_error(
    state: AppState, exc: TechnitiumError, deletions: list[Endpoint], additions: list[Endpoint]
) -> None:
    """Handle errors during record application with failover support.

    Args:
        state: Application state
        exc: Exception that occurred
        deletions: List of endpoints to delete (for retry)
        additions: List of endpoints to add (for retry)

    Raises:
        HTTPException: For various error conditions
    """
    if not _is_connection_error(exc):
        # Not a connection error, return error response
        logger.exception("API error during record application: %s", exc)
        sanitized = sanitize_error_message(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sanitized,
        ) from exc

    # Connection error: attempt failover
    logger.warning(
        "Connection error during record application, attempting failover: %s",
        exc,
    )
    failover_ok, is_writable = await state.try_failover_endpoints()

    if failover_ok and is_writable:
        # Retry with new endpoint
        logger.info("Failover successful to writable endpoint, retrying record changes")
        try:
            await _process_deletions(state, deletions)
            await _process_additions(state, additions)
            # Retry succeeded, update status and return successfully
            await state.update_status(
                ready=True,
                writable=True,
                server_role="primary",
                catalog_membership=None,
            )
            return
        except Exception as retry_exc:
            logger.exception("Retry failed after failover: %s", retry_exc)
            await state.update_status(
                ready=False,
                writable=False,
                server_role=None,
                catalog_membership=None,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable. All failover endpoints failed.",
            ) from retry_exc

    # Failover failed or endpoints not writable
    await state.update_status(
        ready=False,
        writable=False,
        server_role=None,
        catalog_membership=None,
    )

    if failover_ok:
        logger.error("All failover endpoints are read-only; unable to apply record changes")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. No writable Technitium endpoint available.",
        ) from exc

    logger.error("Failover to alternate endpoints failed")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Service temporarily unavailable. Failed to reach any Technitium endpoint.",
    ) from exc


async def apply_record(state: AppState, changes: Changes) -> Response:
    """Apply DNS record changes.

    Args:
        state: Application state
        changes: Changes to apply

    Returns:
        204 No Content on success
    """
    state.ensure_ready()
    state.ensure_writable()

    # Safely log the incoming Changes payload for diagnostics (redacts sensitive keys)
    try:
        # Convert to a serializable structure then log
        if hasattr(changes, "model_dump"):
            changes_dict = changes.model_dump()
        elif hasattr(changes, "dict"):
            changes_dict = changes.dict()
        else:
            changes_dict = dict(changes)
        safe_log_payload("apply_record.changes", changes_dict, logger, level=logging.INFO)
    except Exception:
        logger.info("apply_record received Changes object (failed to serialize)")

    # Combine deletions (delete + updateOld)
    deletions: list[Endpoint] = []
    if changes.delete:
        deletions.extend(changes.delete)
    if changes.update_old:
        deletions.extend(changes.update_old)

    # Combine additions (create + updateNew)
    additions: list[Endpoint] = []
    if changes.create:
        additions.extend(changes.create)
    if changes.update_new:
        additions.extend(changes.update_new)

    # Log the changes received from ExternalDNS
    logger.info(f"apply_record received: {len(deletions)} deletions, {len(additions)} additions")
    for ep in deletions:
        logger.info(f"  DELETE: {ep.dns_name} ({ep.record_type}) -> {ep.targets}")
    for ep in additions:
        logger.info(f"  CREATE: {ep.dns_name} ({ep.record_type}) -> {ep.targets}")

    no_changes = not deletions and not additions
    if no_changes:
        logger.info("All records already up to date, skipping apply")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Attempt to apply changes with failover support
    try:
        # Delegate processing to helpers to reduce cognitive complexity
        await _process_deletions(state, deletions)
        await _process_additions(state, additions)
    except TechnitiumError as exc:
        await _handle_apply_record_error(state, exc, deletions, additions)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _execute_change(
    state: AppState, ep: Endpoint, record_data: dict[str, Any], operation: str
) -> None:
    """Perform a single create/delete operation with circuit breaker handling.

    Abstracted from ``_process_changes`` to reduce its cognitive complexity.

    Raises:
        HTTPException: For circuit breaker open or general errors
        TechnitiumError: Re-raised for connection errors (to be caught by caller)
    """
    # ``client_method`` is either add_record or delete_record.  Giving it
    # a loose Callable type prevents pyright from complaining about the
    # dynamically-added ``ttl`` argument below.
    client_method: Callable[..., Any] = (
        state.client.add_record if operation == "create" else state.client.delete_record
    )
    try:
        if operation == "create":
            await client_method(
                domain=ep.dns_name,
                record_type=ep.record_type,
                record_data=record_data,
                ttl=ep.record_ttl,
            )
        else:
            await client_method(
                domain=ep.dns_name,
                record_type=ep.record_type,
                record_data=record_data,
            )
        dns_records_processed_total.labels(operation=operation).inc()
    except CircuitBreakerOpenError as cboe:
        retry_after = int(cboe.retry_after) if cboe.retry_after and cboe.retry_after > 0 else 0
        headers = {"Retry-After": str(retry_after)} if retry_after > 0 else None
        api_errors_total.labels(error_type="circuit_open").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=API_UNAVAILABLE,
            headers=headers,
        ) from cboe
    except TechnitiumError:
        # Re-raise TechnitiumError so it can be caught by _process_changes or apply_record
        # for failover handling
        raise
    except Exception as e:
        safe_message = sanitize_error_message(e)
        logger.exception(f"Failed to {operation} record {ep.dns_name}: {e}")
        api_errors_total.labels(error_type="connection_error").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {operation} record: {safe_message}",
        ) from e


async def _process_changes(
    state: AppState,
    endpoints: list[Endpoint],
    operation: str,
) -> None:
    """Generic change processor used for both creates and deletes.

    Iterates the ``endpoints`` list and for each target computes the
    :class:`record_data` and then delegates to :func:`_execute_change`.
    The abstraction reduces complexity in this helper by isolating error
    handling into the callee.

    Args:
        state: App state
        endpoints: list of Endpoint objects to act on
        operation: "create" or "delete" used for logging and metrics
    """

    for ep in endpoints:
        for target in ep.targets:
            record_data = _get_record_data(ep.record_type, target)
            if not record_data:
                verb = "creation" if operation == "create" else "deletion"
                logger.warning(
                    f"Skipping {verb} of {ep.dns_name} with invalid record type {ep.record_type}"
                )
                continue

            logger.info(f"{operation.upper()} record {ep.dns_name} with data {record_data}")
            await _execute_change(state, ep, record_data, operation)


async def _process_deletions(state: AppState, deletions: list[Endpoint]) -> None:
    """Process deletion endpoints (wrapper around generic processor)."""
    await _process_changes(state, deletions, "delete")


async def _process_additions(state: AppState, additions: list[Endpoint]) -> None:
    """Process addition endpoints (wrapper around generic processor)."""
    await _process_changes(state, additions, "create")


def _record_data_a(target: str) -> dict[str, Any] | None:
    try:
        ipaddress.IPv4Address(target)
    except ValueError:
        logger.warning(f"Invalid IPv4 address: {target}")
        return None
    return {"ipAddress": target}


def _record_data_aaaa(target: str) -> dict[str, Any] | None:
    try:
        ipaddress.IPv6Address(target)
    except ValueError:
        logger.warning(f"Invalid IPv6 address: {target}")
        return None
    return {"ipAddress": target}


def _record_data_cname(target: str) -> dict[str, Any] | None:
    return {"cname": target}


def _record_data_name(target: str, key: str) -> dict[str, Any] | None:
    """Build a domain-name record field, allowing the DNS root (``.``)."""
    target = target.strip()
    if not target:
        return None
    # Technitium trims the presentation-format trailing dot itself. Keeping
    # it here is important for delete/update calls and for a faithful ``.``
    # root target.
    return {key: target}


def _record_data_txt(target: str) -> dict[str, Any] | None:
    return {"text": target}


def _record_data_aname(target: str) -> dict[str, Any] | None:
    return {"aname": target}


def _record_data_caa(target: str) -> dict[str, Any] | None:
    parts = target.split(maxsplit=2)
    if len(parts) < 3:
        return None
    flags = _parse_uint(parts[0], maximum=255)
    if flags is None:
        return None
    tag = parts[1]
    value = parts[2].strip('"')
    return {"flags": flags, "tag": tag, "value": value}


def _parse_uint(value: str, *, maximum: int = 65535) -> int | None:
    """Parse a DNS unsigned integer with the range used by its wire format."""
    try:
        number = int(value)
    except TypeError:
        return None
    except ValueError:
        return None
    if not 0 <= number <= maximum:
        return None
    return number


def _record_data_uri(target: str) -> dict[str, Any] | None:
    parts = target.split(maxsplit=2)
    if len(parts) < 3:
        return None
    priority = _parse_uint(parts[0])
    weight = _parse_uint(parts[1])
    if priority is None or weight is None:
        return None
    uri = parts[2].strip('"')
    return {"uriPriority": priority, "uriWeight": weight, "uri": uri}


def _record_data_sshfp(target: str) -> dict[str, Any] | None:
    parts = target.split(maxsplit=2)
    if len(parts) < 3:
        return None
    algorithm = _parse_uint(parts[0], maximum=255)
    fp_type = _parse_uint(parts[1], maximum=255)
    if algorithm is None or fp_type is None:
        return None
    algorithm_name = {1: "RSA", 2: "DSA", 3: "ECDSA", 4: "Ed25519", 6: "Ed448"}.get(algorithm)
    fingerprint_type_name = {1: "SHA1", 2: "SHA256"}.get(fp_type)
    fingerprint = parts[2]
    if algorithm_name is None or fingerprint_type_name is None:
        return None
    return {
        "sshfpAlgorithm": algorithm_name,
        "sshfpFingerprintType": fingerprint_type_name,
        "sshfpFingerprint": fingerprint,
    }


def _record_data_svcb_https(target: str) -> dict[str, Any] | None:
    parts = target.split(maxsplit=2)
    if len(parts) < 2:
        return None
    priority = _parse_uint(parts[0])
    if priority is None:
        return None
    target_name = parts[1]
    params = "false"
    if len(parts) > 2:
        svc_fields = _split_rdata_fields(parts[2])
        if svc_fields is None:
            return None
        api_fields: list[str] = []
        for field in svc_fields:
            key, separator, value = field.partition("=")
            if not key:
                return None
            api_fields.extend((key, value if separator else ""))
        params = "|".join(api_fields)
    return {"svcPriority": priority, "svcTargetName": target_name, "svcParams": params}


def _record_data_mx(target: str) -> dict[str, Any] | None:
    parts = target.split()
    if len(parts) != 2:
        return None
    preference = _parse_uint(parts[0])
    if preference is None or not parts[1]:
        return None
    return {"preference": preference, "exchange": parts[1]}


def _record_data_srv(target: str) -> dict[str, Any] | None:
    parts = target.split()
    if len(parts) != 4:
        return None
    priority = _parse_uint(parts[0])
    weight = _parse_uint(parts[1])
    port = _parse_uint(parts[2])
    if priority is None or weight is None or port is None or not parts[3]:
        return None
    return {
        "priority": priority,
        "weight": weight,
        "port": port,
        "target": parts[3],
    }


def _split_rdata_fields(target: str) -> list[str] | None:
    """Split quoted DNS text fields while preserving backslashes in regexps."""
    fields: list[str] = []
    field: list[str] = []
    quoted = False
    token_started = False
    index = 0
    while index < len(target):
        char = target[index]
        if char == '"':
            quoted = not quoted
            token_started = True
        elif char == "\\" and quoted and index + 1 < len(target) and target[index + 1] == '"':
            # A quoted quote is the only escape needed for DNS character
            # strings here; retain all other backslashes (NAPTR regexps use
            # them as significant data).
            field.append('"')
            token_started = True
            index += 1
        elif char.isspace() and not quoted:
            if token_started:
                fields.append("".join(field))
                field = []
                token_started = False
        else:
            field.append(char)
            token_started = True
        index += 1
    if quoted:
        return None
    if token_started:
        fields.append("".join(field))
    return fields


def _record_data_naptr(target: str) -> dict[str, Any] | None:
    parts = _split_rdata_fields(target)
    if parts is None or len(parts) != 6:
        return None
    order = _parse_uint(parts[0])
    preference = _parse_uint(parts[1])
    if order is None or preference is None or not parts[5]:
        return None
    return {
        "naptrOrder": order,
        "naptrPreference": preference,
        "naptrFlags": parts[2],
        "naptrServices": parts[3],
        "naptrRegexp": parts[4],
        "naptrReplacement": parts[5],
    }


def _tlsa_usage_to_number(value: Any) -> str:
    mapping = {"PKIX-TA": "0", "PKIX-EE": "1", "DANE-TA": "2", "DANE-EE": "3"}
    normalized = str(value).replace("_", "-").upper()
    return mapping.get(normalized, str(value))


def _tlsa_selector_to_number(value: Any) -> str:
    mapping = {"CERT": "0", "SPKI": "1"}
    return mapping.get(str(value).upper(), str(value))


def _tlsa_matching_type_to_number(value: Any) -> str:
    mapping = {"FULL": "0", "SHA2-256": "1", "SHA2-512": "2"}
    normalized = str(value).replace("_", "-").upper()
    return mapping.get(normalized, str(value))


def _tlsa_usage_to_name(value: str) -> str | None:
    mapping = {"0": "PKIX-TA", "1": "PKIX-EE", "2": "DANE-TA", "3": "DANE-EE"}
    normalized = value.replace("_", "-").upper()
    if normalized in mapping.values():
        return normalized
    return mapping.get(normalized)


def _tlsa_selector_to_name(value: str) -> str | None:
    mapping = {"0": "Cert", "1": "SPKI"}
    normalized = value.upper()
    if normalized in ("CERT", "SPKI"):
        return "Cert" if normalized == "CERT" else "SPKI"
    return mapping.get(normalized)


def _tlsa_matching_type_to_name(value: str) -> str | None:
    mapping = {"0": "Full", "1": "SHA2-256", "2": "SHA2-512"}
    normalized = value.replace("_", "-").upper()
    if normalized in ("FULL", "SHA2-256", "SHA2-512"):
        return "Full" if normalized == "FULL" else normalized
    return mapping.get(normalized)


def _record_data_tlsa(target: str) -> dict[str, Any] | None:
    parts = target.split()
    if len(parts) != 4:
        return None
    usage = _tlsa_usage_to_name(parts[0])
    selector = _tlsa_selector_to_name(parts[1])
    matching_type = _tlsa_matching_type_to_name(parts[2])
    association_data = parts[3]
    if (
        usage is None
        or selector is None
        or matching_type is None
        or not re.fullmatch(r"[0-9a-fA-F]+", association_data)
        or len(association_data) % 2
    ):
        return None
    return {
        "tlsaCertificateUsage": usage,
        "tlsaSelector": selector,
        "tlsaMatchingType": matching_type,
        "tlsaCertificateAssociationData": association_data,
    }


def _get_record_data(record_type: str, target: str) -> dict[str, Any] | None:
    """Get record data for a given record type and target.

    record_type: DNS record type
    target: Target value

    Returns:
        Record data dict or None if unsupported/invalid
    """
    mapping: dict[str, Callable[[str], dict[str, Any] | None]] = {
        "A": _record_data_a,
        "AAAA": _record_data_aaaa,
        "NS": lambda target: _record_data_name(target, "nameServer"),
        "CNAME": _record_data_cname,
        "PTR": lambda target: _record_data_name(target, "ptrName"),
        "MX": _record_data_mx,
        "TXT": _record_data_txt,
        "SRV": _record_data_srv,
        "NAPTR": _record_data_naptr,
        "DNAME": lambda target: _record_data_name(target, "dname"),
        "TLSA": _record_data_tlsa,
        "ANAME": _record_data_aname,
        "CAA": _record_data_caa,
        "URI": _record_data_uri,
        "SSHFP": _record_data_sshfp,
        "SVCB": _record_data_svcb_https,
        "HTTPS": _record_data_svcb_https,
    }
    handler = mapping.get(record_type)
    if not handler:
        logger.warning(f"Unsupported record type: {record_type}")
        return None
    return handler(target)
