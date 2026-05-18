"""Structured logging + OpenTelemetry helpers for Zoiko services.

All services use structlog with OTel trace context injection so every log line
carries trace_id and span_id.  Services call `configure_logging()` once at
startup (before the first request) and then use `get_logger(__name__)`.
"""
from __future__ import annotations

import logging
import structlog
from opentelemetry import trace


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """Wire structlog + stdlib logging for *service_name*."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            _add_otel_context,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def _add_otel_context(
    logger: object, method: str, event_dict: dict
) -> dict:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
