"""OpenTelemetry and Prometheus observability helpers for the chat-service.

Provides:
  - get_tracer()              — returns a tracer for the chat_service instrumentation scope
  - TOOL_CALLS_COUNTER        — Prometheus counter: allergo_tool_calls_total{session_type, tool_name}
  - TOOL_LATENCY_HISTOGRAM    — Prometheus histogram: allergo_tool_latency_seconds{session_type, tool_name}
  - EVAL_SCORE_GAUGE          — Prometheus gauge: allergo_eval_score{eval_type, metric}
  - setup_telemetry()         — initialise TracerProvider + PrometheusExporter on lifespan startup
  - setup_prometheus()        — expose /metrics endpoint for Prometheus scraping

The OTel TracerProvider is configured via environment variables (standard OTel SDK conventions):
  OTEL_EXPORTER_OTLP_ENDPOINT — OTLP gRPC endpoint (e.g. http://otel-collector:4317)
  OTEL_SERVICE_NAME            — Service name (default: allergo-chat-service)
  OTEL_ENABLED                 — "true" to enable, anything else to use a no-op tracer

Prometheus metrics are always registered — even if OTel is disabled — so that
CI eval jobs can post scores to the allergo_eval_score gauge.
"""

from __future__ import annotations

import os
from typing import Any

from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

# ── Lazy imports for optional dependencies ────────────────────────────────────
# OTel and Prometheus are optional — the service starts without them.
# Missing packages produce a no-op tracer / dummy metrics.

_tracer: Any = None
_prometheus_available: bool = False
_otel_available: bool = False


def _check_otel() -> bool:
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def _check_prometheus() -> bool:
    try:
        import prometheus_client  # noqa: F401
        return True
    except ImportError:
        return False


# ── No-op fallbacks ───────────────────────────────────────────────────────────

class _NoOpSpan:
    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, *args: Any) -> None:
        pass

    def record_exception(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpCounter:
    def labels(self, **kwargs: Any) -> "_NoOpCounter":
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass


class _NoOpHistogram:
    def labels(self, **kwargs: Any) -> "_NoOpHistogram":
        return self

    def observe(self, amount: float) -> None:
        pass


class _NoOpGauge:
    def labels(self, **kwargs: Any) -> "_NoOpGauge":
        return self

    def set(self, value: float) -> None:
        pass


# ── Metrics singletons ────────────────────────────────────────────────────────
# Initialised at module load — will be real Prometheus metrics if prometheus_client
# is available, otherwise no-ops.

TOOL_CALLS_COUNTER: Any = _NoOpCounter()
TOOL_LATENCY_HISTOGRAM: Any = _NoOpHistogram()
EVAL_SCORE_GAUGE: Any = _NoOpGauge()

if _check_prometheus():
    try:
        from prometheus_client import Counter, Histogram, Gauge  # type: ignore

        TOOL_CALLS_COUNTER = Counter(
            "allergo_tool_calls_total",
            "Total number of tool calls made by the chat agent",
            ["session_type", "tool_name"],
        )
        TOOL_LATENCY_HISTOGRAM = Histogram(
            "allergo_tool_latency_seconds",
            "Tool call latency in seconds",
            ["session_type", "tool_name"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        EVAL_SCORE_GAUGE = Gauge(
            "allergo_eval_score",
            "Latest eval score by type and metric (updated by CI eval jobs)",
            ["eval_type", "metric"],
        )
        _prometheus_available = True
        logger.info("prometheus_metrics_registered")
    except Exception as exc:
        logger.warning("prometheus_metrics_registration_failed", error=str(exc))


# ── Tracer accessor ───────────────────────────────────────────────────────────

def get_tracer() -> Any:
    """Return the chat-service tracer. Returns a no-op tracer if OTel is unavailable."""
    global _tracer
    if _tracer is None:
        if _check_otel() and os.environ.get("OTEL_ENABLED", "true").lower() == "true":
            try:
                from opentelemetry import trace  # type: ignore
                _tracer = trace.get_tracer("chat_service", schema_url="https://opentelemetry.io/schemas/1.11.0")
            except Exception as exc:
                logger.warning("otel_tracer_init_failed", error=str(exc))
                _tracer = _NoOpTracer()
        else:
            _tracer = _NoOpTracer()
    return _tracer


# ── Lifespan initialisation ───────────────────────────────────────────────────

def setup_telemetry() -> None:
    """Initialise the OTel TracerProvider with OTLP exporter.

    Call this from the FastAPI lifespan startup handler (api.py).
    Safe to call even if opentelemetry-sdk is not installed.
    """
    if not _check_otel():
        logger.info("otel_sdk_not_installed_skipping_setup")
        return

    if os.environ.get("OTEL_ENABLED", "true").lower() != "true":
        logger.info("otel_disabled_by_env_var")
        return

    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore

        service_name = os.environ.get("OTEL_SERVICE_NAME", "allergo-chat-service")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("otel_otlp_exporter_configured", endpoint=otlp_endpoint)
            except ImportError:
                logger.warning("otlp_grpc_exporter_not_installed")
        else:
            # No OTLP endpoint — use console exporter for local dev
            try:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor  # type: ignore
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                logger.info("otel_console_exporter_configured_for_local_dev")
            except ImportError:
                pass

        trace.set_tracer_provider(provider)
        global _tracer, _otel_available
        _otel_available = True
        _tracer = trace.get_tracer("chat_service")
        logger.info("otel_tracer_provider_configured", service=service_name)

    except Exception as exc:
        logger.warning("otel_setup_failed", error=str(exc))


def setup_prometheus(app: Any) -> None:
    """Add a /metrics endpoint to the FastAPI app for Prometheus scraping.

    Call this from api.py after creating the FastAPI app.
    Safe to call even if prometheus_client is not installed.
    """
    if not _prometheus_available:
        logger.info("prometheus_client_not_installed_skipping_metrics_endpoint")
        return

    try:
        from prometheus_client import make_asgi_app  # type: ignore
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
        logger.info("prometheus_metrics_endpoint_mounted", path="/metrics")
    except Exception as exc:
        logger.warning("prometheus_metrics_endpoint_mount_failed", error=str(exc))
