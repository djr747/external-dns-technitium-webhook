"""Main application entry point."""

import asyncio
import logging
import sys
import threading
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .app_state import AppState
from .config import Config as AppConfig
from .handlers import (
    adjust_endpoints,
    apply_record,
    get_records,
    negotiate_domain_filter,
)
from .middleware import RequestSizeLimitMiddleware, rate_limit_middleware
from .models import Changes, Endpoint, GetZoneOptionsResponse
from .technitium_client import TechnitiumError


class StructuredFormatter(logging.Formatter):
    """Format logs in External-DNS style: time=... level=... module=... msg=..."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured text matching External-DNS format."""
        # ISO 8601 format with Z suffix (UTC)
        timestamp = (
            datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        # Level name in lowercase
        level = record.levelname.lower()

        # Module name (logger name or function name)
        module = record.name if record.name != "root" else record.funcName or "app"

        # Format: time="..." level=info module=handlers msg="..."
        log_parts = [
            f'time="{timestamp}"',
            f"level={level}",
            f"module={module}",
            f'msg="{record.getMessage()}"',
        ]

        return " ".join(log_parts)


# Configure structured logging
def setup_logging() -> None:
    """Set up structured logging matching External-DNS format."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    root_logger.handlers.clear()

    # Create stdout handler with structured formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = StructuredFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


setup_logging()
logger = logging.getLogger(__name__)

logger.debug("main.py imported")

# Coverage hook for testing
try:
    import coverage

    coverage.process_startup()  # pragma: no cover
except ImportError:  # pragma: no cover
    pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager.

    Args:
        app: FastAPI application

    Yields:
        None
    """
    # Startup
    config = AppConfig()

    # Configure logging level
    logging.getLogger().setLevel(config.log_level)
    logger.setLevel(config.log_level)

    # Start health check server in a separate thread
    from .health import create_health_app
    from .server import run_health_server

    health_app = create_health_app()
    logger.info(f"Starting health server on {config.listen_address}:{config.health_port}")
    health_thread = threading.Thread(
        target=run_health_server,
        args=(health_app, config),
        daemon=True,
        name="HealthServerThread",
    )
    health_thread.start()
    logger.info("Health server thread started")

    state = AppState(config)
    app.state.app_state = state

    # Setup Technitium connection
    await setup_technitium_connection(state)

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await state.close()


@dataclass
class ZonePreparationResult:
    """Result of zone preparation on a Technitium endpoint."""

    zone_created: bool
    is_writable: bool
    server_role: str
    catalog_membership: str | None


def _normalize_zone_name(name: str | None) -> str | None:
    """Normalize a DNS zone name for comparison."""

    if not name:
        return None
    normalized = name.strip().rstrip(".")
    return normalized.lower() or None


def get_app_state(app: FastAPI) -> AppState:
    """Get application state from app.

    Args:
        app: FastAPI application

    Returns:
        Application state
    """
    state = getattr(app.state, "app_state", None)
    if not isinstance(state, AppState):
        raise RuntimeError("Application state not initialized")
    return state


def create_state_dependency(app: FastAPI) -> Callable[[], AppState]:
    """Create a dependency that returns the application state.

    Args:
        app: FastAPI application

    Returns:
        Callable dependency returning AppState
    """

    def _get_state() -> AppState:
        return get_app_state(app)

    return _get_state


async def setup_technitium_connection(state: AppState) -> None:
    """Connect to Technitium, supporting failover endpoints and catalog zones.

    If connection fails, the service starts in an unhealthy state (not ready).
    The health check endpoint will return 503 Service Unavailable.
    This allows investigation of issues without complete container failure.
    """

    logger.debug(
        f"Config: verify_ssl={state.config.technitium_verify_ssl}, "
        f"ca_bundle={state.config.technitium_ca_bundle_file}"
    )

    endpoints = state.config.technitium_endpoints
    if not endpoints:
        logger.error("No Technitium endpoints configured; cannot proceed")
        await state.update_status(
            ready=False,
            writable=False,
            server_role=None,
            catalog_membership=None,
        )
        logger.warning("Service starting in unhealthy state. Check configuration and restart.")
        return

    failures: list[str] = []

    for idx, endpoint in enumerate(endpoints, start=1):
        try:
            logger.info(
                "Attempting Technitium endpoint %s (%d/%d)",
                endpoint,
                idx,
                len(endpoints),
            )
            await state.set_active_endpoint(endpoint)

            login_response = await state.client.login(
                username=state.config.technitium_username,
                password=state.config.technitium_password,
            )
            state.client.token = login_response.token
            logger.info("Authenticated with Technitium endpoint %s", endpoint)

            zone_result = await ensure_zone_ready(state)

            await state.update_status(
                ready=True,
                writable=zone_result.is_writable,
                server_role=zone_result.server_role,
                catalog_membership=zone_result.catalog_membership,
            )

            state.start_token_renewal(auto_renew_technitium_token)

            if zone_result.zone_created:
                logger.info(
                    "Zone %s created on endpoint %s",
                    state.config.zone,
                    endpoint,
                )

            if zone_result.catalog_membership:
                logger.info(
                    "Zone %s enrolled in catalog zone %s",
                    state.config.zone,
                    zone_result.catalog_membership,
                )

            if zone_result.is_writable:
                logger.info("Application is ready to serve requests via %s", endpoint)
            else:
                logger.warning(
                    "Endpoint %s is read-only; record changes will be rejected until a writable endpoint is available",
                    endpoint,
                )

            return
        except Exception as exc:  # noqa: BLE001 - ensure we try all endpoints
            logger.error(
                "Failed to initialize Technitium endpoint %s: %s",
                endpoint,
                exc,
                exc_info=True,
            )
            failures.append(f"{endpoint}: {exc}")

    await state.update_status(
        ready=False,
        writable=False,
        server_role=None,
        catalog_membership=None,
    )

    failure_summary = "; ".join(failures) if failures else "unknown error"
    logger.error("Unable to initialize any Technitium endpoint: %s", failure_summary)
    logger.warning(
        "Service starting in unhealthy state. Health check will return 503. "
        "Check logs and fix configuration/network issues, then restart."
    )


async def ensure_zone_ready(state: AppState) -> ZonePreparationResult:
    """Ensure the configured zone exists and is catalog-ready."""

    zone_name = state.config.zone
    catalog = state.config.catalog_zone_name

    zone_options = await _fetch_zone_options(state, zone_name)
    zone_created = False

    if zone_options is None:
        logger.info("Zone %s not found on endpoint, creating...", zone_name)
        await create_default_zone(state)
        zone_created = True
        zone_options = await _fetch_zone_options(state, zone_name)
        if zone_options is None:
            raise RuntimeError(f"Unable to load configuration for zone {zone_name} after creation")

    membership = _normalize_zone_name(zone_options.catalog_zone_name)
    server_role = "secondary" if zone_options.is_read_only else "primary"

    if catalog and not zone_options.is_read_only:
        membership = await ensure_catalog_membership(state, zone_options, catalog)

    return ZonePreparationResult(
        zone_created=zone_created,
        is_writable=not zone_options.is_read_only,
        server_role=server_role,
        catalog_membership=membership,
    )


async def _fetch_zone_options(state: AppState, zone: str) -> GetZoneOptionsResponse | None:
    """Fetch zone options, returning None when zone is missing."""

    try:
        return await state.client.get_zone_options(zone, include_catalog_names=True)
    except TechnitiumError as exc:
        details = str(exc).lower()
        if "not found" in details or "does not exist" in details:
            return None
        raise


async def create_default_zone(state: AppState) -> None:
    """Create the primary zone, preserving backwards-compatible defaults."""

    await state.client.create_zone(
        zone=state.config.zone,
        zone_type="Forwarder",
        protocol="Udp",
        forwarder="this-server",
        dnssec_validation=True,
        catalog=state.config.catalog_zone_name,
    )


async def ensure_catalog_membership(
    state: AppState,
    options: GetZoneOptionsResponse,
    catalog_zone: str,
) -> str | None:
    """Ensure the zone is enrolled in the desired catalog zone."""

    current_membership = _normalize_zone_name(options.catalog_zone_name)
    desired_membership = catalog_zone

    if current_membership == desired_membership:
        return current_membership

    available = {
        name
        for name in (
            _normalize_zone_name(candidate) for candidate in options.available_catalog_zone_names
        )
        if name is not None
    }

    if available and desired_membership not in available:
        logger.warning(
            "Catalog zone %s is not available on endpoint %s; skipping enrollment",
            catalog_zone,
            state.active_endpoint,
        )
        return current_membership

    logger.info(
        "Enrolling zone %s into catalog zone %s",
        state.config.zone,
        catalog_zone,
    )
    await state.client.set_zone_options(
        state.config.zone,
        catalogZoneName=catalog_zone,
    )

    refreshed = await state.client.get_zone_options(
        state.config.zone,
        include_catalog_names=False,
    )
    new_membership = _normalize_zone_name(refreshed.catalog_zone_name)
    if new_membership != desired_membership:
        logger.warning(
            "Catalog enrollment requested for %s but server reports membership %s",
            catalog_zone,
            new_membership,
        )
    return new_membership


async def auto_renew_technitium_token(state: AppState) -> None:
    """Automatically renew the Technitium authentication token.

    Args:
        state: Application state
    """
    DURATION_SUCCESS = 20 * 60  # 20 minutes
    DURATION_FAILURE = 60  # 1 minute

    sleep_for = DURATION_SUCCESS

    while True:
        try:
            await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            logger.debug("Token renewal task cancelled")
            break

        try:
            login_response = await state.client.login(
                username=state.config.technitium_username,
                password=state.config.technitium_password,
            )
            state.client.token = login_response.token
            logger.debug("Successfully renewed Technitium DNS server access token")
            sleep_for = DURATION_SUCCESS
        except Exception:  # noqa: BLE001 - log and retry with backoff
            logger.error("Technitium DNS server renewal failed.")
            sleep_for = DURATION_FAILURE


def create_app() -> FastAPI:
    """Create the FastAPI application.

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="ExternalDNS Technitium Webhook",
        description=(
            "ExternalDNS webhook provider for Technitium DNS Server. "
            "This service enables automatic DNS record synchronization from Kubernetes resources "
            "(Ingress, Service) to Technitium DNS. Supports A, AAAA, CNAME, TXT, ANAME, CAA, URI, "
            "SSHFP, SVCB, and HTTPS record types."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={
            "name": "GitHub Repository",
            "url": "https://github.com/djr747/external-dns-technitium-webhook",
        },
        license_info={
            "name": "MIT",
            "url": "https://github.com/djr747/external-dns-technitium-webhook/blob/main/LICENSE",
        },
    )

    # Add security middleware
    # Rate limiting - configurable per settings
    app.middleware("http")(rate_limit_middleware)

    # Request size limiting - max 1MB
    app.add_middleware(RequestSizeLimitMiddleware, max_size=1024 * 1024)

    # Add CORS middleware with restrictive policy
    # TODO: Configure allow_origins with specific domains for production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://127.0.0.1",
        ],  # TODO: Restrict to specific origins in production
        allow_credentials=False,  # No cookies needed for webhook
        allow_methods=["GET", "POST"],  # Only methods we use
        allow_headers=["Content-Type"],
        max_age=3600,
    )

    # Routes
    state_dependency = create_state_dependency(app)

    @app.get("/")
    async def domain_filter(
        state: AppState = Depends(state_dependency),
    ) -> Response:
        """Negotiate domain filter."""
        return await negotiate_domain_filter(state)

    @app.get("/records")
    async def records(
        state: AppState = Depends(state_dependency),
    ) -> Response:
        """Get current DNS records."""
        return await get_records(state)

    @app.post("/adjustendpoints")
    async def adjust(
        endpoints: list[Endpoint],
        state: AppState = Depends(state_dependency),
    ) -> Response:
        """Adjust endpoints."""
        return await adjust_endpoints(state, endpoints)

    @app.post("/records", status_code=204)
    async def apply(
        changes: Changes,
        state: AppState = Depends(state_dependency),
    ) -> None:
        """Apply DNS record changes."""
        await apply_record(state, changes)

    return app


# Module-level app export for ASGI servers (uvicorn, etc.)
app = create_app()


def main() -> None:
    from .health import create_health_app  # pragma: no cover
    from .server import run_servers  # pragma: no cover

    health_app = create_health_app()
    config = AppConfig()
    run_servers(app, health_app, config)


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover
