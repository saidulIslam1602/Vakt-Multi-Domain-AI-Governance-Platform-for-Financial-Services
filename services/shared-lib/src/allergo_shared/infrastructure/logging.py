"""Structured logging configuration using structlog + OpenTelemetry."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """Configure structured JSON logging for production and human-readable for local dev."""

    def _add_logger_name(
        logger: Any, method: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        """Safe drop-in for structlog.stdlib.add_logger_name that works with PrintLogger."""
        if hasattr(logger, "name"):
            event_dict["logger"] = logger.name
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            _add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
