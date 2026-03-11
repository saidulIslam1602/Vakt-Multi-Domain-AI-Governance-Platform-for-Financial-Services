"""Health check helpers — reusable across all FastAPI services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from fastapi import APIRouter
from fastapi.responses import JSONResponse


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class HealthCheck:
    name: str
    checker: Callable[[], Awaitable[bool]]


@dataclass
class HealthResult:
    status: HealthStatus
    checks: dict[str, str] = field(default_factory=dict)


def make_health_router(
    service_name: str,
    version: str,
    checks: list[HealthCheck] | None = None,
) -> APIRouter:
    """Return a /health router with liveness and readiness endpoints."""

    router = APIRouter(tags=["health"])

    @router.get("/health/live", include_in_schema=False)
    async def liveness() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": service_name})

    @router.get("/health/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        if not checks:
            return JSONResponse(
                {"status": "ok", "service": service_name, "version": version}
            )
        results: dict[str, str] = {}
        overall = HealthStatus.OK
        for check in checks:
            try:
                ok = await check.checker()
                results[check.name] = "ok" if ok else "degraded"
                if not ok:
                    overall = HealthStatus.DEGRADED
            except Exception as exc:
                results[check.name] = f"error: {exc}"
                overall = HealthStatus.DOWN

        status_code = 200 if overall == HealthStatus.OK else 503
        return JSONResponse(
            {"status": str(overall), "service": service_name, "checks": results},
            status_code=status_code,
        )

    return router
