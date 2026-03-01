"""Circuit breaker implementation for resilient Technitium API calls."""

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and rejects a request."""

    def __init__(self, state: CircuitState, retry_after: float) -> None:
        """Initialize error.

        Args:
            state: Current circuit state
            retry_after: Seconds until circuit may transition to half-open
        """
        self.state = state
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker is {state.value}; retry after {retry_after:.1f}s")


class CircuitBreaker:
    """Thread-safe async circuit breaker for protecting external API calls.

    States:
        CLOSED:    Normal operation - requests pass through.
        OPEN:      Failure threshold exceeded - requests rejected immediately.
        HALF_OPEN: Timeout elapsed - one test request allowed through.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening the circuit.
            timeout: Seconds to wait in OPEN state before moving to HALF_OPEN.
        """
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")

        self._failure_threshold = failure_threshold
        self._timeout = timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()
        # When in HALF_OPEN only a single test request may be in-flight.
        self._half_open_inflight = False

    @property
    def state(self) -> CircuitState:
        """Current circuit state (read-only snapshot)."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Current consecutive failure count."""
        return self._failure_count

    def _seconds_until_half_open(self) -> float:
        """Return remaining seconds before the circuit can try half-open."""
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        remaining = self._timeout - elapsed
        return max(0.0, remaining)

    async def _check_state(self) -> None:
        """Transition OPEN → HALF_OPEN when the timeout has elapsed.

        Raises:
            CircuitBreakerOpenError: When the circuit is still open.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                remaining = self._seconds_until_half_open()
                if remaining > 0:
                    raise CircuitBreakerOpenError(self._state, remaining)
                # Timeout elapsed - move to HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                # No test request is in-flight yet.
                self._half_open_inflight = False
                logger.info("Circuit breaker transitioning OPEN → HALF_OPEN after timeout")
            # If we're in HALF_OPEN, only a single caller may proceed as the
            # test request. Subsequent callers should be rejected until that
            # test completes (either success or failure).
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_inflight:
                    raise CircuitBreakerOpenError(self._state, 0.0)
                # Mark that a test request is now in-flight and allow it through.
                self._half_open_inflight = True

    async def _on_success(self) -> None:
        """Record a successful call; reset the breaker when in HALF_OPEN."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
                # Clear the half-open in-flight marker when closing the circuit.
                self._half_open_inflight = False
                logger.info(
                    "Circuit breaker transitioning HALF_OPEN → CLOSED after successful request"
                )
            elif self._state == CircuitState.CLOSED:
                # Reset failure counter on success while closed
                self._failure_count = 0
                # Ensure the half-open marker is not left set.
                self._half_open_inflight = False

    async def _on_failure(self) -> None:
        """Record a failed call; open the circuit if threshold is reached."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately reopens the circuit
                self._state = CircuitState.OPEN
                # Clear the half-open in-flight marker when reopening.
                self._half_open_inflight = False
                logger.warning(
                    "Circuit breaker transitioning HALF_OPEN → OPEN after test request failure"
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker transitioning CLOSED → OPEN after %d consecutive failures",
                    self._failure_count,
                )

    async def call(self, coro: Any) -> Any:
        """Execute *coro* through the circuit breaker.

        Args:
            coro: Awaitable to execute.

        Returns:
            The result of awaiting *coro*.

        Raises:
            CircuitBreakerOpenError: When the circuit is open.
            Exception: Re-raised from *coro* after recording the failure.
        """
        try:
            await self._check_state()
        except CircuitBreakerOpenError:
            # Close the unawaited coroutine to prevent runtime warnings when
            # the circuit rejects the request before it is ever awaited.
            coro.close()
            raise
        try:
            result = await coro
        except Exception:
            await self._on_failure()
            raise
        await self._on_success()
        return result
