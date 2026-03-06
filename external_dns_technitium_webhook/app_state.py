"""Application state management."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from . import middleware
from .config import Config
from .middleware import RateLimiter
from .resilience import CircuitBreaker
from .technitium_client import TechnitiumClient

logger = logging.getLogger(__name__)


class AppState:
    """Global application state."""

    is_ready: bool
    client: TechnitiumClient
    active_endpoint: str
    is_writable: bool
    server_role: str | None
    catalog_membership: str | None

    def __init__(self, config: Config) -> None:
        """Initialize application state.

        Args:
            config: Application configuration
        """
        self.config = config
        self.is_ready = False
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            timeout=config.circuit_breaker_timeout,
        )
        self.client = TechnitiumClient(
            base_url=config.technitium_url,
            timeout=config.technitium_timeout,
            verify_ssl=config.technitium_verify_ssl,
            ca_bundle=config.technitium_ca_bundle_file,
            enable_request_compression=config.technitium_enable_request_compression,
            compression_threshold_bytes=config.technitium_compression_threshold_bytes,
            circuit_breaker=self.circuit_breaker,
            records_cache_ttl_seconds=config.records_cache_ttl_seconds,
        )
        # Use provided helper to replace the module-level rate limiter.
        # This avoids a direct module-level assignment which some static
        # analysis tools may flag as an ineffectual statement.
        middleware.set_rate_limiter(
            RateLimiter(
                requests_per_minute=config.requests_per_minute,
                burst=config.rate_limit_burst,
            )
        )
        self._lock = asyncio.Lock()
        self._token_task: asyncio.Task[None] | None = None
        self._failback_task: asyncio.Task[None] | None = None
        self.active_endpoint = self.client.base_url
        self.is_writable = False
        self.server_role: str | None = None
        self.catalog_membership = None
        # Lightweight in-memory counters for basic operational metrics.
        # These are intentionally simple so they are safe to use in tests
        # and in environments without a metrics backend. Projects that
        # want structured metrics can wire a Prometheus client or similar
        # and use these fields as hooks.
        self.record_fetch_count = 0

    def ensure_ready(self) -> None:
        """Ensure the application is ready.

        Raises:
            RuntimeError: If the application is not ready
        """
        if not self.is_ready:
            raise RuntimeError("Service not ready yet. Try again later.")

    def ensure_writable(self) -> None:
        """Ensure the connected Technitium endpoint is writable."""

        self.ensure_ready()
        if not self.is_writable:
            raise RuntimeError("Technitium endpoint is read-only")

    async def close(self) -> None:
        """Close the application state."""
        tasks_to_cancel = []
        if self._token_task:
            self._token_task.cancel()
            tasks_to_cancel.append(self._token_task)
        if self._failback_task:
            self._failback_task.cancel()
            tasks_to_cancel.append(self._failback_task)
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        await self.client.close()

    async def set_active_endpoint(self, base_url: str) -> None:
        """Reconfigure the API client for a new Technitium endpoint."""

        normalized = base_url.rstrip("/")
        if self.client.base_url == normalized:
            self.active_endpoint = normalized
            return

        old_client = self.client
        self.client = TechnitiumClient(
            base_url=normalized,
            timeout=self.config.technitium_timeout,
            verify_ssl=self.config.technitium_verify_ssl,
            ca_bundle=self.config.technitium_ca_bundle_file,
            enable_request_compression=self.config.technitium_enable_request_compression,
            compression_threshold_bytes=self.config.technitium_compression_threshold_bytes,
            circuit_breaker=self.circuit_breaker,
            records_cache_ttl_seconds=self.config.records_cache_ttl_seconds,
        )
        self.active_endpoint = normalized
        await old_client.close()

    def start_token_renewal(self, renewer: Callable[[AppState], Coroutine[Any, Any, None]]) -> None:
        """Start the background token renewal loop if not already running."""

        if self._token_task and not self._token_task.done():
            return
        self._token_task = asyncio.create_task(renewer(self))

    def start_failback_attempts(
        self, failback_task: Callable[[AppState], Coroutine[Any, Any, None]]
    ) -> None:
        """Start the background failback attempt loop if not already running."""

        if self._failback_task and not self._failback_task.done():
            return
        self._failback_task = asyncio.create_task(failback_task(self))

    async def update_status(
        self,
        *,
        ready: bool,
        writable: bool,
        server_role: str | None,
        catalog_membership: str | None,
    ) -> None:
        """Update readiness metadata for the webhook."""

        async with self._lock:
            self.is_ready = ready
            self.is_writable = writable
            self.server_role = server_role
            self.catalog_membership = catalog_membership

    async def _authenticate_with_endpoint(self, endpoint: str) -> None:
        """Authenticate with the given endpoint.

        Args:
            endpoint: The endpoint to authenticate with

        Raises:
            Exception: If authentication fails
        """
        login_response = await self.client.login(
            username=self.config.technitium_username,
            password=self.config.technitium_password,
        )
        self.client.token = login_response.token
        logger.info("Successfully authenticated with failover endpoint %s", endpoint)

    async def _try_endpoint_failover(
        self, endpoint: str, current_endpoint: str
    ) -> tuple[bool, bool]:
        """Attempt failover to a single endpoint.

        Args:
            endpoint: The endpoint to try
            current_endpoint: The currently active endpoint (for logging)

        Returns:
            Tuple of (success, is_writable). If success is False, is_writable is undefined.
        """
        try:
            logger.info(
                "Attempting failover to endpoint %s (from %s)",
                endpoint,
                current_endpoint,
            )
            await self.set_active_endpoint(endpoint)
            await self._authenticate_with_endpoint(endpoint)

            # Check zone status to determine if this node is primary or secondary
            is_writable, server_role, catalog_membership = await self._check_zone_status(endpoint)

            # Reset circuit breaker for the new endpoint
            self.circuit_breaker.reset()

            # Update application status with the new endpoint's cluster role
            await self.update_status(
                ready=True,
                writable=is_writable,
                server_role=server_role,
                catalog_membership=catalog_membership,
            )

            return (True, is_writable)
        except Exception as exc:
            logger.warning(
                "Failover to endpoint %s failed: %s",
                endpoint,
                exc,
                exc_info=True,
            )
            return (False, False)

    async def try_failover_endpoints(self) -> tuple[bool, bool]:
        """Attempt failover to alternate Technitium endpoints.

        Tries each configured endpoint in order (excluding the currently active
        endpoint) and attempts to authenticate. On success, updates the active
        endpoint and returns True. If all endpoints fail or no alternatives
        exist, returns False.

        When successful, also checks zone read-only status to determine if the
        new endpoint is a primary (writable) or secondary (read-only) node in
        a cluster.

        Returns:
            Tuple of (failover_ok, is_writable). If failover_ok is False,
            is_writable value is undefined.
        """
        endpoints = self.config.technitium_endpoints
        current_endpoint = self.client.base_url
        failures: list[str] = []

        for endpoint in endpoints:
            if endpoint == current_endpoint:
                # Skip the current endpoint
                continue

            success, is_writable = await self._try_endpoint_failover(endpoint, current_endpoint)
            if success:
                return (True, is_writable)

            failures.append(endpoint)

        if failures:
            failure_summary = "; ".join(failures)
            logger.error("All failover attempts failed: %s", failure_summary)
        else:
            logger.warning("No failover endpoints available (all are the current endpoint)")

        return (False, False)

    async def _check_zone_status(self, endpoint: str) -> tuple[bool, str, str | None]:
        """Check zone read-only status and catalog membership for an endpoint.

        Args:
            endpoint: The endpoint being checked (for logging)

        Returns:
            Tuple of (is_writable, server_role, catalog_membership)
        """
        from .models import GetZoneOptionsResponse

        is_writable = True
        server_role = "primary"
        catalog_membership = None

        try:
            zone_options: GetZoneOptionsResponse | None = await self.client.get_zone_options(
                self.config.zone, include_catalog_names=True
            )
            if zone_options:
                is_writable = not zone_options.is_read_only
                server_role = "secondary" if zone_options.is_read_only else "primary"
                catalog_membership = zone_options.catalog_zone_name
                if catalog_membership and isinstance(catalog_membership, str):
                    catalog_membership = (
                        catalog_membership.rstrip(".") if catalog_membership != "." else None
                    )
        except Exception as zone_check_exc:
            logger.warning(
                "Could not determine zone status on endpoint %s: %s",
                endpoint,
                zone_check_exc,
            )

        return (is_writable, server_role, catalog_membership)

    async def try_failback_to_primary(self) -> bool:
        """Attempt failback to the primary (first configured) Technitium endpoint.

        This method is called periodically to detect when a previously-failed primary
        endpoint has recovered and is ready to accept traffic again. If successful,
        updates the active endpoint and returns True.

        Returns:
            True if failback to primary succeeded, False otherwise
        """
        endpoints = self.config.technitium_endpoints
        if not endpoints:
            return False

        primary_endpoint = endpoints[0]
        current_endpoint = self.client.base_url

        # If already on primary, nothing to do
        if primary_endpoint == current_endpoint:
            return False

        try:
            logger.info(
                "Attempting failback to primary endpoint %s (currently on %s)",
                primary_endpoint,
                current_endpoint,
            )
            await self.set_active_endpoint(primary_endpoint)

            # Test connectivity and authentication
            login_response = await self.client.login(
                username=self.config.technitium_username,
                password=self.config.technitium_password,
            )
            self.client.token = login_response.token

            # Check zone status to ensure primary is writable
            is_writable, server_role, catalog_membership = await self._check_zone_status(
                primary_endpoint
            )

            # Only failback if primary is writable (not a read-only replica)
            if not is_writable:
                logger.info(
                    "Primary endpoint %s is read-only; staying on current %s endpoint",
                    primary_endpoint,
                    "writable" if self.is_writable else "read-only",
                )
                # Fall back to secondary
                await self.set_active_endpoint(current_endpoint)
                # Re-authenticate with secondary
                try:
                    login_response = await self.client.login(
                        username=self.config.technitium_username,
                        password=self.config.technitium_password,
                    )
                    self.client.token = login_response.token
                except Exception:
                    pass  # Secondary should still work
                return False

            logger.info("Successfully failed back to primary endpoint %s", primary_endpoint)

            # Update application status with primary's cluster role
            await self.update_status(
                ready=True,
                writable=is_writable,
                server_role=server_role,
                catalog_membership=catalog_membership,
            )

            return True
        except Exception as exc:
            logger.debug(
                "Failback to primary endpoint %s not yet ready: %s",
                primary_endpoint,
                exc,
            )
            # Failback failed, stay on current endpoint
            return False
