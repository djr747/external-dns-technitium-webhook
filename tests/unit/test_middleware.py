"""Unit tests for middleware."""

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.middleware import (
    RateLimiter,
    RequestSizeLimitMiddleware,
    rate_limit_middleware,
)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    """Create rate limiter for testing."""
    return RateLimiter(requests_per_minute=60, burst=10)


@pytest.fixture
def app_with_middleware() -> FastAPI:
    """Create FastAPI app with middleware for testing."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/test")
    async def test_post(data: dict[str, str]) -> dict[str, str]:
        return {"received": data.get("message", "")}

    # Add middleware
    app.middleware("http")(rate_limit_middleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_size=1024)  # type: ignore[arg-type]

    return app


@pytest.mark.asyncio
async def test_rate_limiter_init(rate_limiter: RateLimiter) -> None:
    """Test rate limiter initialization."""
    assert rate_limiter.rate == 1.0  # 60 requests/minute = 1/second
    assert rate_limiter.burst == 10.0
    assert len(rate_limiter.tokens) == 0
    assert len(rate_limiter.last_update) == 0


@pytest.mark.asyncio
async def test_rate_limiter_allows_first_request(rate_limiter: RateLimiter) -> None:
    """Test rate limiter allows first request."""
    result = await rate_limiter.check_rate_limit("client1")
    assert result is True


@pytest.mark.asyncio
async def test_rate_limiter_burst_capacity(rate_limiter: RateLimiter) -> None:
    """Test rate limiter burst capacity."""
    # Burst of 10 requests should all succeed
    client_id = "burst_client"
    for i in range(10):
        result = await rate_limiter.check_rate_limit(client_id)
        assert result is True, f"Request {i + 1} should succeed"

    # 11th request should fail (exceeded burst)
    result = await rate_limiter.check_rate_limit(client_id)
    assert result is False


@pytest.mark.asyncio
async def test_rate_limiter_token_refill(rate_limiter: RateLimiter) -> None:
    """Test that tokens refill over time."""
    client_id = "refill_client"

    # Use up burst capacity
    for _ in range(10):
        await rate_limiter.check_rate_limit(client_id)

    # Should fail immediately
    result = await rate_limiter.check_rate_limit(client_id)
    assert result is False

    # Wait for 2 seconds to refill tokens (rate = 1 token/second)
    await asyncio.sleep(2.1)

    # Should now allow requests again
    result = await rate_limiter.check_rate_limit(client_id)
    assert result is True


@pytest.mark.asyncio
async def test_rate_limiter_different_clients(rate_limiter: RateLimiter) -> None:
    """Test rate limiter tracks clients separately."""
    # Client 1 uses up burst
    for _ in range(10):
        await rate_limiter.check_rate_limit("client1")

    # Client 1 should be rate limited
    assert await rate_limiter.check_rate_limit("client1") is False

    # Client 2 should still have full capacity
    assert await rate_limiter.check_rate_limit("client2") is True


def test_rate_limit_middleware_allows_normal_requests(app_with_middleware: FastAPI) -> None:
    """Test rate limit middleware allows normal requests."""
    client = TestClient(app_with_middleware)

    # First request should succeed
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_middleware_blocks_excessive_requests() -> None:
    """Test rate limit middleware blocks excessive requests."""
    # Create fresh app with isolated rate limiter to avoid shared state
    app = FastAPI()
    local_limiter = RateLimiter(requests_per_minute=60, burst=10)

    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    # Create custom middleware function with local rate limiter
    async def local_rate_limit_middleware(request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not await local_limiter.check_rate_limit(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    app.middleware("http")(local_rate_limit_middleware)
    client = TestClient(app)

    # Make 10 requests (burst limit) - all should succeed
    for i in range(10):
        response = client.get("/test")
        assert response.status_code == 200, f"Request {i + 1} should succeed"

    # 11th request should be rate limited - use pytest.raises since TestClient re-raises the exception
    with pytest.raises(HTTPException) as exc_info:
        client.get("/test")

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_request_size_limit_allows_small_requests() -> None:
    """Test request size limit allows small requests."""
    # Create fresh app for this test to avoid shared state
    app = FastAPI()

    @app.post("/test")
    async def test_post(data: dict[str, str]) -> dict[str, str]:
        return {"received": data.get("message", "")}

    # Add only size limit middleware
    app.add_middleware(RequestSizeLimitMiddleware, max_size=1024)  # type: ignore[arg-type]

    client = TestClient(app)

    # Small payload should succeed
    response = client.post("/test", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json() == {"received": "hello"}


def test_request_size_limit_blocks_large_requests() -> None:
    """Test request size limit blocks large requests."""
    # Create fresh app for this test
    app = FastAPI()

    @app.post("/test")
    async def test_post(data: dict[str, str]) -> dict[str, str]:
        return {"received": data.get("message", "")}

    # Add only size limit middleware with small limit
    app.add_middleware(RequestSizeLimitMiddleware, max_size=10)  # type: ignore[arg-type]

    client = TestClient(app)

    # Create payload larger than 1KB limit
    large_message = "x" * 2000
    response = client.post(
        "/test",
        json={"message": large_message},
        headers={"Content-Length": str(len(large_message) + 100)},
    )
    assert response.status_code == 413  # HTTP 413 Content Too Large


def test_request_size_limit_no_content_length() -> None:
    """Test request size limit when no Content-Length header."""
    app = FastAPI()

    @app.post("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(RequestSizeLimitMiddleware, max_size=1024)  # type: ignore[arg-type]
    client = TestClient(app)

    # Request without Content-Length should still work
    response = client.post("/test", json={"data": "test"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_request_size_limit_middleware_init() -> None:
    """Test request size limit middleware initialization."""
    app = FastAPI()
    middleware = RequestSizeLimitMiddleware(app, max_size=2048)
    assert middleware.max_size == 2048
    assert middleware.app == app


@pytest.mark.asyncio
async def test_rate_limiter_max_burst_refill(rate_limiter: RateLimiter) -> None:
    """Test rate limiter doesn't exceed burst capacity on refill."""
    client_id = "max_burst_client"

    # Use some tokens
    for _ in range(5):
        await rate_limiter.check_rate_limit(client_id)

    # Wait longer than needed to refill
    await asyncio.sleep(20)  # Way more than needed

    # Should have max burst tokens, not unlimited
    for i in range(10):
        result = await rate_limiter.check_rate_limit(client_id)
        assert result is True, f"Request {i + 1} should succeed"

    # 11th should fail (capped at burst)
    result = await rate_limiter.check_rate_limit(client_id)
    assert result is False


@pytest.mark.asyncio
async def test_rate_limit_middleware_returns_429_when_limited(
    mocker: MockerFixture,
) -> None:
    """Global rate limit middleware should raise HTTP 429 when over the limit."""

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    }
    request = Request(scope)

    mocker.patch(
        "external_dns_technitium_webhook.middleware.rate_limiter.check_rate_limit",
        new_callable=AsyncMock,
        return_value=False,
    )

    async def call_next(_: Request) -> Response:
        return Response(status_code=200)

    with pytest.raises(HTTPException) as exc_info:
        await rate_limit_middleware(request, call_next)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_request_size_limit_invalid_content_length() -> None:
    """Invalid content-length headers should be treated as oversized requests."""

    app = FastAPI()
    middleware = RequestSizeLimitMiddleware(app, max_size=10)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-length", b"invalid")],
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)

    async def call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 413
