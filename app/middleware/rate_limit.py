"""Rate limiting middleware."""
import time
import logging
from typing import Dict, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.settings import settings


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""
    requests: list = field(default_factory=list)


class RateLimiter:
    """In-memory rate limiter using sliding window."""

    def __init__(self):
        # Store: {endpoint: {client_ip: RateLimitBucket}}
        self.buckets: Dict[str, Dict[str, RateLimitBucket]] = defaultdict(
            lambda: defaultdict(RateLimitBucket)
        )
        self.logger = logging.getLogger("app.ratelimit")

    def is_allowed(
        self,
        client_ip: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int]:
        """
        Check if request is allowed under rate limit.

        Args:
            client_ip: Client IP address
            endpoint: API endpoint identifier
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        now = time.time()
        bucket = self.buckets[endpoint][client_ip]

        # Remove expired timestamps
        bucket.requests = [
            ts for ts in bucket.requests
            if now - ts < window_seconds
        ]

        # Check if under limit
        if len(bucket.requests) < max_requests:
            bucket.requests.append(now)
            return True, 0

        # Calculate retry after
        oldest_request = min(bucket.requests)
        retry_after = int(window_seconds - (now - oldest_request)) + 1

        return False, retry_after

    def reset(self):
        """Reset all rate limit buckets (for testing)."""
        self.buckets.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting to specific endpoints."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("app.ratelimit")

        # Define rate limit rules
        self.rate_limits = {
            "/api/auth/login": (
                settings.RATE_LIMIT_AUTH_REQUESTS,
                settings.RATE_LIMIT_AUTH_WINDOW
            ),
            "/api/auth/register": (
                settings.RATE_LIMIT_AUTH_REQUESTS,
                settings.RATE_LIMIT_AUTH_WINDOW
            ),
            "/auth/login": (
                settings.RATE_LIMIT_AUTH_REQUESTS,
                settings.RATE_LIMIT_AUTH_WINDOW
            ),
            "/auth/register": (
                settings.RATE_LIMIT_AUTH_REQUESTS,
                settings.RATE_LIMIT_AUTH_WINDOW
            ),
            "/api/rag/query": (
                settings.RATE_LIMIT_RAG_REQUESTS,
                settings.RATE_LIMIT_RAG_WINDOW
            ),
            "/api/rag/search": (
                settings.RATE_LIMIT_RAG_REQUESTS,
                settings.RATE_LIMIT_RAG_WINDOW
            ),
        }

    async def dispatch(self, request: Request, call_next):
        """Check rate limits before processing request."""
        # Skip if rate limiting disabled
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Check if endpoint has rate limit
        path = request.url.path
        if path in self.rate_limits:
            max_requests, window_seconds = self.rate_limits[path]

            # Check rate limit
            allowed, retry_after = rate_limiter.is_allowed(
                client_ip=client_ip,
                endpoint=path,
                max_requests=max_requests,
                window_seconds=window_seconds
            )

            if not allowed:
                self.logger.warning(
                    f"Rate limit exceeded for {client_ip} on {path}",
                    extra={
                        'request_id': getattr(request.state, 'request_id', None),
                        'extra_fields': {
                            'client_ip': client_ip,
                            'endpoint': path,
                            'retry_after': retry_after
                        }
                    }
                )

                # Return 429 Too Many Requests
                return Response(
                    content=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)}
                )

        # Process request
        return await call_next(request)
