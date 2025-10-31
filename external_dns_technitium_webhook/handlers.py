"""API handlers for ExternalDNS webhook endpoints."""

import ipaddress
import logging
import re
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse, Response

from .app_state import AppState
from .models import Changes, DomainFilter, Endpoint

logger = logging.getLogger(__name__)


def sanitize_error_message(error: Exception) -> str:
    """Sanitize error message to prevent information disclosure.

    Removes sensitive patterns like passwords, tokens, file paths, etc.

    Args:
        error: Original exception

    Returns:
        Safe error message for client response
    """
    error_str = str(error)

    # Remove sensitive patterns
    sensitive_patterns = [
        (r"password[=:]\s*\S+", "password=***"),
        (r"token[=:]\s*\S+", "token=***"),
        (r"api[_-]?key[=:]\s*\S+", "api_key=***"),
        (r"secret[=:]\s*\S+", "secret=***"),
        (r"auth[=:]\s*\S+", "auth=***"),
        (r"/home/[^/\s]+", "/home/***"),
        (r"/Users/[^/\s]+", "/Users/***"),
        (r"C:\\Users\\[^\\s]+", r"C:\\Users\\***"),
    ]

    for pattern, replacement in sensitive_patterns:
        error_str = re.sub(pattern, replacement, error_str, flags=re.IGNORECASE)

    return error_str


class ExternalDNSResponse(JSONResponse):
    """Custom JSON response with ExternalDNS content type."""

    media_type = "application/external.dns.webhook+json;version=1"


async def health_check(state: AppState) -> Response:
    """Health check endpoint.

    Args:
        state: Application state

    Returns:
        200 OK if ready, 503 if not ready
    """
    try:
        await state.ensure_ready()
        return Response(status_code=status.HTTP_200_OK)
    except RuntimeError as e:
        logger.warning(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e


async def negotiate_domain_filter(state: AppState) -> ExternalDNSResponse:
    """Negotiate domain filters with ExternalDNS.

    Args:
        state: Application state

    Returns:
        Domain filter configuration
    """
    await state.ensure_ready()

    domain_filter = DomainFilter(
        filters=state.config.domain_filter_list,
        exclude=[],
    )

    logger.debug(f"Negotiated domain filters: {domain_filter.filters}")
    return ExternalDNSResponse(content=domain_filter.model_dump())


async def get_records(state: AppState) -> ExternalDNSResponse:
    """Get current DNS records.

    Args:
        state: Application state

    Returns:
        List of current endpoints
    """
    await state.ensure_ready()

    logger.debug("Fetching DNS records")

    response = await state.client.get_records(
        domain=state.config.zone,
        list_zone=True,
    )

    endpoints: list[Endpoint] = []
    for record in response.records:
        record_type = record.type
        r_data = record.r_data

        # Skip unsupported record types
        if record_type not in (
            "A",
            "AAAA",
            "CNAME",
            "TXT",
            "ANAME",
            "CAA",
            "URI",
            "SSHFP",
            "SVCB",
            "HTTPS",
        ):
            continue

        endpoint = Endpoint(
            dnsName=record.name,
            recordType=record_type,
            recordTTL=record.ttl,
            setIdentifier="",
            targets=[],
        )

        # Extract target from record data
        if record_type == "A" or record_type == "AAAA":
            endpoint.targets = [r_data.get("ipAddress", "")]
        elif record_type == "CNAME":
            endpoint.targets = [r_data.get("cname", "")]
        elif record_type == "TXT":
            endpoint.targets = [r_data.get("text", "")]
        elif record_type == "ANAME":
            endpoint.targets = [r_data.get("aname", "")]
        elif record_type == "CAA":
            # Format: flags tag "value"
            flags = r_data.get("flags", 0)
            tag = r_data.get("tag", "")
            value = r_data.get("value", "")
            endpoint.targets = [f'{flags} {tag} "{value}"']
        elif record_type == "URI":
            # Format: priority weight "uri"
            priority = r_data.get("priority", 0)
            weight = r_data.get("weight", 0)
            uri = r_data.get("uri", "")
            endpoint.targets = [f'{priority} {weight} "{uri}"']
        elif record_type == "SSHFP":
            # Format: algorithm fptype fingerprint
            algorithm = r_data.get("algorithm", 0)
            fp_type = r_data.get("fingerprintType", 0)
            fingerprint = r_data.get("fingerprint", "")
            endpoint.targets = [f"{algorithm} {fp_type} {fingerprint}"]
        elif record_type in ("SVCB", "HTTPS"):
            # Format: priority target params
            priority = r_data.get("svcPriority", 0)
            target = r_data.get("svcTargetName", "")
            params = r_data.get("svcParams", "")
            endpoint.targets = [f"{priority} {target} {params}".strip()]

        endpoints.append(endpoint)

    logger.debug(f"Found {len(endpoints)} endpoints")
    return ExternalDNSResponse(content=[ep.model_dump(by_alias=True) for ep in endpoints])


async def adjust_endpoints(state: AppState, endpoints: list[Endpoint]) -> ExternalDNSResponse:
    """Adjust endpoints before applying changes.

    Args:
        state: Application state
        endpoints: Endpoints to adjust

    Returns:
        Adjusted endpoints (no changes in this implementation)
    """
    await state.ensure_ready()

    # We don't do any endpoint adjustment
    return ExternalDNSResponse(content=[ep.model_dump(by_alias=True) for ep in endpoints])


async def apply_record(state: AppState, changes: Changes) -> Response:
    """Apply DNS record changes.

    Args:
        state: Application state
        changes: Changes to apply

    Returns:
        204 No Content on success
    """
    await state.ensure_ready()
    await state.ensure_writable()

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

    if not deletions and not additions:
        logger.info("All records already up to date, skipping apply")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Process deletions
    for ep in deletions:
        for target in ep.targets:
            record_data = _get_record_data(ep.record_type, target)
            if not record_data:
                logger.warning(
                    f"Skipping deletion of {ep.dns_name} with invalid record type {ep.record_type}"
                )
                continue

            logger.info(f"Deleting record {ep.dns_name} with data {record_data}")
            try:
                await state.client.delete_record(
                    domain=ep.dns_name,
                    record_type=ep.record_type,
                    record_data=record_data,
                )
            except Exception as e:
                safe_message = sanitize_error_message(e)
                logger.error(f"Failed to delete record {ep.dns_name}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to delete record: {safe_message}",
                ) from e

    # Process additions
    for ep in additions:
        for target in ep.targets:
            record_data = _get_record_data(ep.record_type, target)
            if not record_data:
                logger.warning(
                    f"Skipping creation of {ep.dns_name} with invalid record type {ep.record_type}"
                )
                continue

            logger.info(f"Adding record {ep.dns_name} with data {record_data}")
            try:
                await state.client.add_record(
                    domain=ep.dns_name,
                    record_type=ep.record_type,
                    record_data=record_data,
                    ttl=ep.record_ttl,
                )
            except Exception as e:
                safe_message = sanitize_error_message(e)
                logger.error(f"Failed to add record {ep.dns_name}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to add record: {safe_message}",
                ) from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_record_data(record_type: str, target: str) -> dict[str, Any] | None:
    """Get record data for a given record type and target.

    Args:
        record_type: DNS record type
        target: Target value

    Returns:
        Record data dict or None if unsupported/invalid
    """
    if record_type == "A":
        # Validate IPv4
        try:
            ipaddress.IPv4Address(target)
        except (ipaddress.AddressValueError, ValueError):
            logger.warning(f"Invalid IPv4 address: {target}")
            return None
        return {"ipAddress": target}
    elif record_type == "AAAA":
        # Validate IPv6
        try:
            ipaddress.IPv6Address(target)
        except (ipaddress.AddressValueError, ValueError):
            logger.warning(f"Invalid IPv6 address: {target}")
            return None
        return {"ipAddress": target}
    elif record_type == "CNAME":
        return {"cname": target}
    elif record_type == "TXT":
        return {"text": target}
    elif record_type == "ANAME":
        return {"aname": target}
    elif record_type == "CAA":
        # Parse: flags tag "value"
        parts = target.split(maxsplit=2)
        if len(parts) < 3:
            return None
        flags = int(parts[0])
        tag = parts[1]
        value = parts[2].strip('"')
        return {"flags": flags, "tag": tag, "value": value}
    elif record_type == "URI":
        # Parse: priority weight "uri"
        parts = target.split(maxsplit=2)
        if len(parts) < 3:
            return None
        priority = int(parts[0])
        weight = int(parts[1])
        uri = parts[2].strip('"')
        return {"uriPriority": priority, "uriWeight": weight, "uri": uri}
    elif record_type == "SSHFP":
        # Parse: algorithm fptype fingerprint
        parts = target.split(maxsplit=2)
        if len(parts) < 3:
            return None
        algorithm = int(parts[0])
        fp_type = int(parts[1])
        fingerprint = parts[2]
        return {
            "algorithm": algorithm,
            "fingerprintType": fp_type,
            "fingerprint": fingerprint,
        }
    elif record_type in ("SVCB", "HTTPS"):
        # Parse: priority target [params]
        parts = target.split(maxsplit=2)
        if len(parts) < 2:
            return None
        priority = int(parts[0])
        target_name = parts[1]
        params = parts[2] if len(parts) > 2 else ""
        return {
            "svcPriority": priority,
            "svcTargetName": target_name,
            "svcParams": params,
        }
    return None
