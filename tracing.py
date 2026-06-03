"""
Dynatrace OpenTelemetry tracing and metrics setup.

Exports traces and metrics to Dynatrace via OTLP HTTP and enables
Traceloop / OpenLLMetry instrumentation for LangChain and OpenAI.

Required environment variables:
    DT_API_URL   - Dynatrace OTLP base endpoint, e.g.
                   https://<env>.live.dynatrace.com/api/v2/otlp
    DT_API_TOKEN - Dynatrace API token with openTelemetryTrace.ingest
                   and metrics.ingest scopes
"""

import logging
import os

from opentelemetry import metrics as otel_metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from traceloop.sdk import Traceloop
except ImportError:
    Traceloop = None

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False


def setup_tracing(service_name: str = "research-assistant") -> None:
    """
    Configure OpenTelemetry traces and metrics with Dynatrace as the backend
    and initialize Traceloop/OpenLLMetry for LangChain and OpenAI instrumentation.

    Sets both the global TracerProvider and MeterProvider so all downstream
    calls to trace.get_tracer() and metrics.get_meter() export to Dynatrace.

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
    resource = Resource.create({"service.name": service_name})

    # Build the span exporter once and hand it to Traceloop so it does not
    # create a second OTLP trace exporter pointing at a different endpoint.
    span_exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/v1/traces",
        headers=auth_headers,
    )

    if Traceloop is not None:
        # Traceloop.init() registers LangChain/OpenAI instrumentation patches
        # and sets the global TracerProvider using our exporter.
        # Passing exporter= (not api_endpoint=) ensures no second OTLP
        # exporter is created internally.
        Traceloop.init(
            app_name=service_name,
            exporter=span_exporter,
        )
        logger.info("Traceloop initialized for AI observability")
    else:
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        logger.warning(
            "traceloop-sdk not installed; LangChain spans will not be captured"
        )

    # Configure the MeterProvider explicitly after Traceloop.init() to take
    # ownership of the global. Traceloop may have set one internally; we
    # replace it so all metric export uses our configured exporter and
    # resource attributes.
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{base_url}/v1/metrics",
        headers=auth_headers,
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
    )
    otel_metrics.set_meter_provider(meter_provider)
    logger.info("Metrics exporter configured for Dynatrace")

    _TRACING_INITIALIZED = True
