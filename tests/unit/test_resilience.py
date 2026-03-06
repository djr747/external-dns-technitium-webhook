"""Unit tests for the circuit breaker (resilience.py)."""

import asyncio
import time

import pytest

from external_dns_technitium_webhook.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _succeed(value: int = 42) -> int:
    """Coroutine that succeeds immediately."""
    return value


async def _fail(exc: Exception | None = None) -> None:
    """Coroutine that raises *exc* (default RuntimeError)."""
    raise exc or RuntimeError("simulated failure")


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_circuit_breaker_defaults() -> None:
    """Default parameters produce a closed breaker."""
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_invalid_threshold() -> None:
    """failure_threshold < 1 should raise ValueError."""
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0)


def test_circuit_breaker_invalid_timeout() -> None:
    """timeout <= 0 should raise ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        CircuitBreaker(timeout=0)


# ---------------------------------------------------------------------------
# CLOSED state – normal operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closed_state_passes_requests() -> None:
    """Requests pass through when the circuit is closed."""
    cb = CircuitBreaker(failure_threshold=3)
    result = await cb.call(_succeed(99))
    assert result == 99
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_closed_state_resets_count_on_success() -> None:
    """A successful call resets the failure counter."""
    cb = CircuitBreaker(failure_threshold=5)
    # Cause a couple of failures but not enough to open the circuit
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_fail())
    assert cb.failure_count == 3

    # A successful call should reset the counter
    await cb.call(_succeed())
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CLOSED → OPEN transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_threshold_opens_circuit() -> None:
    """Reaching the failure threshold transitions CLOSED → OPEN."""
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_fail())

    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3


@pytest.mark.asyncio
async def test_circuit_open_rejects_immediately() -> None:
    """Once open, the circuit rejects requests with CircuitBreakerOpenError."""
    cb = CircuitBreaker(failure_threshold=2, timeout=60.0)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_fail())

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await cb.call(_succeed())

    assert exc_info.value.state == CircuitState.OPEN
    assert exc_info.value.retry_after > 0


@pytest.mark.asyncio
async def test_circuit_breaker_open_error_message() -> None:
    """CircuitBreakerOpenError should mention state and retry_after."""
    cb = CircuitBreaker(failure_threshold=1, timeout=60.0)
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await cb.call(_succeed())

    msg = str(exc_info.value)
    assert "open" in msg
    assert "retry after" in msg


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_transitions_to_half_open_after_timeout() -> None:
    """After the timeout elapses the circuit moves to HALF_OPEN."""
    cb = CircuitBreaker(failure_threshold=1, timeout=0.05)  # 50 ms timeout
    with pytest.raises(RuntimeError):
        await cb.call(_fail())
    assert cb.state == CircuitState.OPEN

    await asyncio.sleep(0.1)  # Wait longer than the timeout

    # The next call should be allowed through (triggers HALF_OPEN check)
    result = await cb.call(_succeed())
    assert result == 42
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_open_state_before_timeout_still_rejects() -> None:
    """Requests are still rejected while the timeout has not elapsed."""
    cb = CircuitBreaker(failure_threshold=1, timeout=60.0)
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(_succeed())

    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN state behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit() -> None:
    """A successful request in HALF_OPEN transitions back to CLOSED."""
    cb = CircuitBreaker(failure_threshold=1, timeout=0.05)
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    await asyncio.sleep(0.1)

    # This call should be tried as the circuit is now half-open
    result = await cb.call(_succeed())
    assert result == 42
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit() -> None:
    """A failed request in HALF_OPEN transitions back to OPEN."""
    cb = CircuitBreaker(failure_threshold=1, timeout=0.05)
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    # Wait for timeout so the circuit naturally moves to HALF_OPEN
    await asyncio.sleep(0.1)

    # The circuit is now HALF_OPEN; a failure here should reopen it
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_half_open_allows_only_single_test_request() -> None:
    """When HALF_OPEN only a single test request may be in-flight."""
    cb = CircuitBreaker(failure_threshold=1, timeout=0.01)
    # Cause the circuit to open
    with pytest.raises(RuntimeError):
        await cb.call(_fail())

    # Wait for timeout so the circuit moves to HALF_OPEN
    await asyncio.sleep(0.02)

    # Start two concurrent calls; one should proceed as the test request,
    # the other should be rejected immediately with CircuitBreakerOpenError.
    async def _slow_success(val: int) -> int:
        await asyncio.sleep(0.02)
        return val

    t1 = asyncio.create_task(cb.call(_slow_success(1)))
    t2 = asyncio.create_task(cb.call(_succeed(2)))

    results = await asyncio.gather(t1, t2, return_exceptions=True)

    # Exactly one succeeded and the other is a CircuitBreakerOpenError
    assert any(isinstance(r, CircuitBreakerOpenError) for r in results)
    assert any(r == 1 or r == 2 for r in results)

    # After a successful half-open test the circuit should be closed
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Integration with health check handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_reflects_circuit_open() -> None:
    """health_check returns 503 when the circuit breaker is open."""
    import json
    from unittest.mock import MagicMock

    from external_dns_technitium_webhook.handlers import health_check

    state = MagicMock()
    state.is_ready = True
    cb = CircuitBreaker(failure_threshold=1, timeout=60.0)
    # Open the circuit
    with pytest.raises(RuntimeError):
        await cb.call(_fail())
    state.circuit_breaker = cb

    response = health_check(state)
    assert response.status_code == 503

    raw_body = response.body
    body_bytes = raw_body.tobytes() if isinstance(raw_body, memoryview) else raw_body or b""
    data = json.loads(body_bytes)
    assert data.get("circuit_breaker") == "open"


@pytest.mark.asyncio
async def test_health_check_ok_when_circuit_closed() -> None:
    """health_check returns 200 when ready and circuit is closed."""
    from unittest.mock import MagicMock

    from external_dns_technitium_webhook.handlers import health_check

    state = MagicMock()
    state.is_ready = True
    state.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)

    response = health_check(state)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# CircuitBreakerOpenError attributes
# ---------------------------------------------------------------------------


def test_circuit_breaker_open_error_attributes() -> None:
    """CircuitBreakerOpenError exposes state and retry_after."""
    err = CircuitBreakerOpenError(CircuitState.OPEN, 42.5)
    assert err.state == CircuitState.OPEN
    assert err.retry_after == pytest.approx(42.5)


# ---------------------------------------------------------------------------
# seconds_until_half_open helper
# ---------------------------------------------------------------------------


def test_seconds_until_half_open_no_failure() -> None:
    """Returns 0 when no failure has been recorded."""
    cb = CircuitBreaker(failure_threshold=5, timeout=60.0)
    assert cb._seconds_until_half_open() == 0.0


def test_seconds_until_half_open_after_failure() -> None:
    """Returns a positive value just after a failure is recorded."""
    cb = CircuitBreaker(failure_threshold=5, timeout=60.0)
    cb._last_failure_time = time.monotonic()
    remaining = cb._seconds_until_half_open()
    assert 0 < remaining <= 60.0


def test_circuit_breaker_reset() -> None:
    """Test circuit breaker reset functionality."""
    cb = CircuitBreaker(failure_threshold=5, timeout=60)

    # Transition to OPEN state
    cb._state = CircuitState.OPEN
    cb._failure_count = 5
    cb._last_failure_time = 123.456
    cb._half_open_inflight = True

    # Reset
    cb.reset()

    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 0
    assert cb._last_failure_time is None
    assert cb._half_open_inflight is False


@pytest.mark.asyncio
async def test_on_success_while_open() -> None:
    """Test _on_success call when state is already OPEN."""
    cb = CircuitBreaker()
    cb._state = CircuitState.OPEN
    await cb._on_success()
    # It should not change state simply because an old request succeeded
    assert cb._state == CircuitState.OPEN
