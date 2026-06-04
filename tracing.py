"""
OpenTelemetry tracing and metrics setup via OTLP HTTP.

Exports traces and metrics to an OTLP-compatible backend and enables
Traceloop / OpenLLMetry instrumentation for LangChain and OpenAI.

Required environment variables:
    DT_API_URL   - OTLP base endpoint (no trailing slash), e.g.
                   https://<env>.live.dynatrace.com/api/v2/otlp
    DT_API_TOKEN - API token with openTelemetryTrace.ingest
                   and metrics.ingest scopes
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.jaeger_baggage import JaegerBaggagePropagator
from opentelemetry.propagators.w3c_trace_context import W3CTraceContextPropagator
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from traceloop.sdk import Traceloop
except ImportError:
    Traceloop = None

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False

# Configure global propagators for W3C trace context extraction from HTTP headers.
# This must happen before tracing is initialized so that incoming traceparent headers
# from OneAgent (via nginx) are extracted and used as parent context for all spans.
set_global_textmap(CompositePropagator([
    W3CTraceContextPropagator(),
    JaegerBaggagePropagator(),
]))


def setup_tracing(service_name: str = "research-assistant") -> None:
    """
    Configure OpenTelemetry traces and metrics via OTLP HTTP and initialize
    Traceloop/OpenLLMetry for LangChain and OpenAI instrumentation.

    When Traceloop is available, it owns both the TracerProvider and MeterProvider.
    The DELTA temporality env var is set before Traceloop.init() so its internally
    created OTLPMetricExporter also picks up the correct setting for Dynatrace.

    Raises:
        ValueError: If DT_API_URL or DT_API_TOKEN are not set.
    """
    global _TRACING_INITIALIZED

    if _TRACING_INITIALIZED:
        logger.debug("Tracing already initialized; skipping re-initialization")
        return

    dt_api_url = os.environ.get("DT_API_URL")
    dt_api_token = os.environ.get("DT_API_TOKEN")

    if not dt_api_url:
        raise ValueError(
            "DT_API_URL not set. Provide your Dynatrace OTLP base endpoint."
        )
    if not dt_api_token:
        raise ValueError(
            "DT_API_TOKEN not set. Provide a token with "
            "openTelemetryTrace.ingest and metrics.ingest scopes."
        )

    base_url = dt_api_url.rstrip("/")
    auth_headers = {"Authorization": f"Api-Token {dt_api_token}"}

    # Dynatrace rejects CUMULATIVE monotonic sums (UNSUPPORTED_METRIC_TYPE_MONOTONIC_CUMULATIVE_SUM).
    # The OTel HTTP exporter defaults to CUMULATIVE. Setting this env var before any exporter is
    # created ensures both Traceloop's internal exporter and any manual exporter use DELTA.
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta")

    if Traceloop is not None:
        # api_endpoint (not exporter=) keeps Traceloop's LLM metrics instrumentation active.
        # Passing exporter= instead silences metrics entirely at the Traceloop level.
        # Traceloop owns both TracerProvider and MeterProvider; the OTel SDK prevents
        # overriding the MeterProvider once set.
        Traceloop.init(
            app_name=service_name,
            api_endpoint=base_url,
            headers=auth_headers,
        )
        logger.info("Traceloop initialized for AI observability")
    else:
        resource = Resource.create({"service.name": service_name})
        span_exporter = OTLPSpanExporter(
            endpoint=f"{base_url}/v1/traces",
            headers=auth_headers,
        )
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        logger.warning(
            "traceloop-sdk not installed; LangChain spans will not be captured"
        )

    _TRACING_INITIALIZED = True
