"""Infrastructure adapters and utilities for Allergo Nordic services."""

from allergo_shared.infrastructure.rate_limit import (
    RateLimitMiddleware,
    make_rate_limit_dependency,
)

__all__ = ["RateLimitMiddleware", "make_rate_limit_dependency"]
