"""Application state management."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from . import middleware
from .config import Config
from .middleware import RateLimiter
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
        self.client = TechnitiumClient(
            base_url=config.technitium_url,
            timeout=config.technitium_timeout,
            verify_ssl=config.technitium_verify_ssl,
            ca_bundle=config.technitium_ca_bundle_file,
            enable_request_compression=config.technitium_enable_request_compression,
            compression_threshold_bytes=config.technitium_compression_threshold_bytes,
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

    async def ensure_ready(self) -> None:
        """Ensure the application is ready.

        Raises:
            RuntimeError: If the application is not ready
        """
        if not self.is_ready:
            raise RuntimeError("Service not ready yet. Try again later.")

    async def ensure_writable(self) -> None:
        """Ensure the connected Technitium endpoint is writable."""

        await self.ensure_ready()
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
