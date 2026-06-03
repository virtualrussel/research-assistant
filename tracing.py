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
from opentelemetry.metrics import (
    Counter,
    Histogram,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
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

    if Traceloop is not None:
        # api_endpoint (not exporter=) keeps Traceloop's LLM metrics
        # instrumentation active. Passing exporter= instead silences metrics
        # entirely at the Traceloop level.
        Traceloop.init(
            app_name=service_name,
            api_endpoint=base_url,
            headers=auth_headers,
        )
        logger.info("Traceloop initialized for AI observability")
    else:
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

    # Override the MeterProvider set by Traceloop to take full ownership of
    # the metrics pipeline. The explicit View ensures all histogram instruments
    # use ExplicitBucketHistogramAggregation — Dynatrace's OTLP ingestion
    # rejects ExponentialHistogram, which some OTel instrumentations emit by
    # default.
    # Dynatrace rejects CUMULATIVE monotonic sums (UNSUPPORTED_METRIC_TYPE_MONOTONIC_CUMULATIVE_SUM).
    # The OTel HTTP exporter defaults to CUMULATIVE, so we override to DELTA for all
    # sum and histogram instruments. Gauges remain CUMULATIVE (instantaneous value semantics).
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{base_url}/v1/metrics",
        headers=auth_headers,
        preferred_temporality={
            Counter: AggregationTemporality.DELTA,
            UpDownCounter: AggregationTemporality.DELTA,
            Histogram: AggregationTemporality.DELTA,
            ObservableCounter: AggregationTemporality.DELTA,
            ObservableUpDownCounter: AggregationTemporality.DELTA,
            ObservableGauge: AggregationTemporality.CUMULATIVE,
        },
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
        views=[
            View(
                instrument_type=Histogram,
                aggregation=ExplicitBucketHistogramAggregation(),
            )
        ],
    )
    otel_metrics.set_meter_provider(meter_provider)
    logger.info("Metrics exporter configured for Dynatrace")

    _TRACING_INITIALIZED = True
