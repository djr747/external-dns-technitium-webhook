"""Response types for the ExternalDNS webhook."""

from fastapi.responses import JSONResponse


class ExternalDNSResponse(JSONResponse):
    """Custom JSON response with ExternalDNS content type."""

    media_type = "application/external.dns.webhook+json;version=1"
