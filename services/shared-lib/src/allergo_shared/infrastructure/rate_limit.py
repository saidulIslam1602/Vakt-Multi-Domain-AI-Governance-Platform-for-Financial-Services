"""Tenant-aware rate limiting middleware for FastAPI services.

Algorithm: sliding-window token bucket implemented with a simple in-process
counter dictionary.  For multi-instance deployments, consider swapping the
storage backend to Azure Cache for Redis (see ``RedisBucketStore`` stub).

Usage
-----
In any FastAPI service ``api.py``::

    from allergo_shared.infrastructure.rate_limit import RateLimitMiddleware

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,   # per tenant per minute
        burst_multiplier=2,       # allow short bursts up to 2× the base rate
    )

For development / tests, call with ``enabled=False`` to disable all limiting.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Paths that are always exempt from rate limiting
_EXEMPT_PATHS = frozenset(
    [
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    ]
)


class _TokenBucket:
    """Per-tenant sliding-window token bucket.

    Each bucket starts full.  One token is consumed per request.  Tokens
    refill at a constant rate (``rate_per_second`` tokens / second) up to
    ``capacity``.
    """

    __slots__ = ("_capacity", "_tokens", "_rate", "_last_refill", "_lock")

    def __init__(self, capacity: float, rate_per_second: float) -> None:
        self._capacity = capacity
        self._tokens = capacity  # start full
        self._rate = rate_per_second
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self) -> bool:
        """Return True if a token was consumed (request allowed), False if throttled."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._rate
            )
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    @property
    def tokens_remaining(self) -> int:
        return max(0, math.floor(self._tokens))

    @property
    def retry_after_seconds(self) -> int:
        """Seconds until at least one token is available."""
        deficit = 1.0 - self._tokens
        return max(1, math.ceil(deficit / self._rate))


class _InMemoryBucketStore:
    """Thread-safe in-memory store for per-tenant token buckets."""

    def __init__(self, capacity: float, rate_per_second: float) -> None:
        self._capacity = capacity
        self._rate = rate_per_second
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(self._capacity, self._rate)
        )

    def get(self, tenant_id: str) -> _TokenBucket:
        return self._buckets[tenant_id]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI middleware that enforces per-tenant request limits.

    Args:
        app: The ASGI application to wrap.
        requests_per_minute: Maximum sustained requests per tenant per minute.
        burst_multiplier: Allow short bursts up to this multiple of the base
            rate.  Defaults to 2 (i.e. up to 2× RPM in a single burst).
        enabled: Set to False to disable all throttling (local dev / tests).
        tenant_id_extractor: Optional callable ``(request) -> str`` to derive
            the tenant ID.  Defaults to reading the ``X-Tenant-ID`` header;
            falls back to ``"anonymous"`` if the header is absent.
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        burst_multiplier: float = 2.0,
        enabled: bool = True,
        tenant_id_extractor: Callable[[Request], str] | None = None,
    ) -> None:
        super().__init__(app)
        self._enabled = enabled
        capacity = requests_per_minute * burst_multiplier
        rate_per_second = requests_per_minute / 60.0
        self._store = _InMemoryBucketStore(capacity, rate_per_second)
        self._extractor = tenant_id_extractor or _default_tenant_extractor

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = self._extractor(request)
        bucket = self._store.get(tenant_id)
        allowed = await bucket.consume()

        if not allowed:
            retry_after = bucket.retry_after_seconds
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "tenant_id": tenant_id,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(int(self._store._capacity)),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response: Response = await call_next(request)
        # Annotate successful responses with rate-limit headers
        response.headers["X-RateLimit-Remaining"] = str(bucket.tokens_remaining)
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_tenant_extractor(request: Request) -> str:
    """Extract tenant ID from the ``X-Tenant-ID`` header.

    Falls back to the JWT ``tenant_id`` claim stored in ``request.state``
    by the auth middleware (if already decoded), then to ``"anonymous"``.
    """
    explicit = request.headers.get("X-Tenant-ID")
    if explicit:
        return explicit

    # Check if the auth middleware stored the user on request.state
    user: Any = getattr(request.state, "user", None)
    if user is not None:
        tid: Any = getattr(user, "tenant_id", None)
        if tid is not None:
            return str(tid)

    return "anonymous"


# ---------------------------------------------------------------------------
# FastAPI dependency (alternative to middleware for route-level control)
# ---------------------------------------------------------------------------


def make_rate_limit_dependency(
    requests_per_minute: int = 60,
    burst_multiplier: float = 2.0,
) -> Callable[[Request], Awaitable[None]]:
    """Return a FastAPI dependency that applies rate limiting to individual routes.

    Prefer the middleware approach for global limiting; use this for per-route
    overrides (e.g. stricter limits on expensive AI endpoints).

    Example::

        router = APIRouter()
        ai_rate_limit = make_rate_limit_dependency(requests_per_minute=10)

        @router.post("/chat", dependencies=[Depends(ai_rate_limit)])
        async def chat_endpoint(body: ChatRequest) -> ChatResponse: ...
    """
    store = _InMemoryBucketStore(
        capacity=requests_per_minute * burst_multiplier,
        rate_per_second=requests_per_minute / 60.0,
    )

    async def _dependency(request: Request) -> None:
        tenant_id = _default_tenant_extractor(request)
        bucket = store.get(tenant_id)
        allowed = await bucket.consume()
        if not allowed:
            retry_after = bucket.retry_after_seconds
            raise JSONResponse(  # type: ignore[misc]
                status_code=429,
                content={
                    "detail": "Rate limit exceeded.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    return _dependency
