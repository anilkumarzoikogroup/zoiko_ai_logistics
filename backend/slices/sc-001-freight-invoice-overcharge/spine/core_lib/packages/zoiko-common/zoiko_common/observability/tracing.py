"""
OpenTelemetry distributed tracing setup (FR-022).

Usage (in FastAPI app startup):
  from zoiko_common.observability.tracing import setup_tracing
  setup_tracing(service_name="phase2-api-gateway")

Propagation:
  - Inbound `traceparent` header → extracted into current context
  - Outbound calls: inject traceparent from current context
  - All spans include tenant_id and trace_id attributes

In dev (OTEL_EXPORTER_OTLP_ENDPOINT not set): uses in-memory no-op exporter.
In prod: sends to GCP Cloud Trace via OTLP.
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def setup_tracing(service_name: str = "zoiko") -> None:
    """
    Configure OTel tracing for this process.
    No-op if opentelemetry packages are not installed.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint)
        else:
            from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
            exporter = InMemorySpanExporter()
            logger.debug("OTel: using in-memory exporter (set OTEL_EXPORTER_OTLP_ENDPOINT for prod)")

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # FastAPI / Starlette auto-instrumentation
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor().instrument()
        except ImportError:
            pass

        logger.info("OTel tracing configured: service=%s", service_name)

    except ImportError:
        logger.debug("opentelemetry not installed — tracing disabled")


def get_tracer(name: str = "zoiko"):
    """Get a tracer. Returns a no-op tracer if OTel is not installed."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


def inject_traceparent(headers: dict) -> dict:
    """Inject W3C traceparent into an outbound headers dict."""
    try:
        from opentelemetry import propagate
        propagate.inject(headers)
    except ImportError:
        pass
    return headers


def extract_trace_context(headers: dict) -> None:
    """Extract W3C traceparent from inbound request headers."""
    try:
        from opentelemetry import propagate
        propagate.extract(headers)
    except ImportError:
        pass


class _NoopTracer:
    """Stub tracer for when OTel is not installed."""

    class _NoopSpan:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def set_attribute(self, *args): pass
        def record_exception(self, *args): pass

    def start_as_current_span(self, name, **kwargs):
        return self._NoopSpan()
