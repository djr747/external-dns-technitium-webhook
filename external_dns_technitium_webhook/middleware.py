"""Middleware for security and request handling."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API endpoints.

    Implements a token bucket algorithm to limit requests per client.
    Each client gets a bucket of tokens that refills over time.
    """

    def __init__(self, requests_per_minute: int = 1000, burst: int = 10):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum sustained requests per minute per client
            burst: Maximum burst size (tokens in bucket)
        """
        self.rate = requests_per_minute / 60.0  # Tokens per second
        self.burst = float(burst)
        self.tokens: dict[str, float] = defaultdict(lambda: self.burst)
        self.last_update: dict[str, datetime] = defaultdict(datetime.now)
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, client_id: str) -> bool:
        """Check if request is within rate limit.

        Args:
            client_id: Unique client identifier (usually IP address)

        Returns:
            True if within limit, False if rate limit exceeded
        """
        async with self._lock:
            now = datetime.now()
            time_passed = (now - self.last_update[client_id]).total_seconds()

            # Add tokens based on time passed (refill bucket)
            self.tokens[client_id] = min(
                self.burst, self.tokens[client_id] + time_passed * self.rate
            )
            self.last_update[client_id] = now

            # Check if we have tokens available
            if self.tokens[client_id] >= 1.0:
                self.tokens[client_id] -= 1.0
                return True

            # Rate limit exceeded
            logger.warning(
                f"Rate limit exceeded for client {client_id}. Tokens: {self.tokens[client_id]:.2f}"
            )
            return False


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=1000, burst=10)


def set_rate_limiter(rl: RateLimiter) -> None:
    """Replace the module-level rate_limiter with a new instance.

    Static analysis tools may flag direct assignments to module-level variables
    (e.g., `middleware.rate_limiter = ...`) as potentially ineffective ("ineffectual statement")
    since they could be overlooked or misunderstood. This helper function makes the
    replacement explicit and intentional, and is the supported way for other modules
    to replace the global RateLimiter instance.
    """
    global rate_limiter
    rate_limiter = rl


async def rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Rate limiting middleware for FastAPI.

    Applies rate limiting per client IP address.
    Returns 429 Too Many Requests if limit is exceeded.

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler in chain

    Returns:
        Response from next handler or 429 error

    Raises:
        HTTPException: 429 status if rate limit exceeded
    """
    # Use client IP as identifier
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    if not await rate_limiter.check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": "60"},
        )

    # Proceed with request
    response: Response = await call_next(request)
    return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size.

    Prevents memory exhaustion from large payloads.
    """

    def __init__(self, app: ASGIApp, max_size: int = 1024 * 1024) -> None:
        """Initialize middleware.

        Args:
            app: ASGI application
            max_size: Maximum request body size in bytes
        """
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Validate incoming requests before passing to the application."""

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = self.max_size + 1

            if length > self.max_size:
                return JSONResponse(
                    {"detail": "Request too large"},
                    status_code=413,
                )

        return await call_next(request)
