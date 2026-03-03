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
        if self._token_task:
            self._token_task.cancel()
            await asyncio.gather(self._token_task, return_exceptions=True)
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

    async def try_failover_endpoints(self) -> bool:
        """Attempt failover to alternate Technitium endpoints.

        Tries each configured endpoint in order (excluding the currently active
        endpoint) and attempts to authenticate. On success, updates the active
        endpoint and returns True. If all endpoints fail or no alternatives
        exist, returns False.

        Returns:
            True if failover to an alternate endpoint succeeded, False otherwise
        """
        endpoints = self.config.technitium_endpoints
        current_endpoint = self.client.base_url
        failures: list[str] = []

        for endpoint in endpoints:
            if endpoint == current_endpoint:
                # Skip the current endpoint
                continue

            try:
                logger.info(
                    "Attempting failover to endpoint %s (from %s)",
                    endpoint,
                    current_endpoint,
                )
                await self.set_active_endpoint(endpoint)

                # Test connectivity and authentication
                login_response = await self.client.login(
                    username=self.config.technitium_username,
                    password=self.config.technitium_password,
                )
                self.client.token = login_response.token
                logger.info("Successfully authenticated with failover endpoint %s", endpoint)

                # Reset circuit breaker for the new endpoint
                self.circuit_breaker.reset()

                return True
            except Exception as exc:
                logger.warning(
                    "Failover to endpoint %s failed: %s",
                    endpoint,
                    exc,
                    exc_info=True,
                )
                failures.append(f"{endpoint}: {exc}")

        if failures:
            failure_summary = "; ".join(failures)
            logger.error("All failover attempts failed: %s", failure_summary)
        else:
            logger.warning("No failover endpoints available (all are the current endpoint)")

        return False
