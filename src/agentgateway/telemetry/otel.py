"""OpenTelemetry tracing integration for the gateway pipeline."""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

logger = logging.getLogger(__name__)


class GatewayTracer:
    """
    Wraps OpenTelemetry tracing for the gateway pipeline.

    Creates spans for each stage: auth, policy, guardrails, obo, proxy.
    """

    def __init__(self, enabled: bool = False, endpoint: str | None = None) -> None:
        self._enabled = enabled
        self._tracer: trace.Tracer | None = None

        if enabled:
            resource = Resource.create({"service.name": "agentgateway"})
            provider = TracerProvider(resource=resource)

            # Console exporter for demo
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

            # OTLP exporter for production
            if endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
                    provider.add_span_processor(SimpleSpanProcessor(otlp_exporter))
                except ImportError:
                    logger.warning("OTLP exporter not installed — using console only")

            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer("agentgateway")
            logger.info("OpenTelemetry tracing enabled")

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a new trace span."""
        if not self._enabled or not self._tracer:
            return _NoOpSpan()
        return self._tracer.start_span(name, attributes=attributes)

    def start_as_current_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a span as the current active span (context manager)."""
        if not self._enabled or not self._tracer:
            return _NoOpContextManager()
        return self._tracer.start_as_current_span(name, attributes=attributes)


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass

    def end(self) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoOpContextManager:
    """No-op context manager for when tracing is disabled."""

    async def __aenter__(self) -> _NoOpSpan:
        return _NoOpSpan()

    async def __aexit__(self, *args: Any) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return _NoOpSpan()

    def __exit__(self, *args: Any) -> None:
        pass
