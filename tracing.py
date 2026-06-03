"""
Dynatrace OpenTelemetry tracing setup.

Exports traces to Dynatrace via OTLP HTTP and enables Traceloop /
OpenLLMetry instrumentation for AI frameworks such as LangChain.

Required environment variables:
    DT_API_URL   - e.g. https://<env>.live.dynatrace.com/api/v2/otlp
    DT_API_TOKEN - Dynatrace API token with openTelemetryTrace.ingest scope
"""

import logging
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
    Configure OpenTelemetry tracing with Dynatrace as the backend and
    initialize Traceloop/OpenLLMetry for AI framework instrumentation.

    Sets the global TracerProvider so all subsequent calls to
    trace.get_tracer() will export spans to Dynatrace.

    Args:
        service_name: The service name as it will appear in Dynatrace.

    Raises:
        ValueError: If DT_API_URL or DT_API_TOKEN are not set.
    """
    global _TRACING_INITIALIZED

    if _TRACING_INITIALIZED:
        logger.info("Tracing already initialized; skipping re-initialization")
        return

    dt_api_url = os.environ.get("DT_API_URL")
    dt_api_token = os.environ.get("DT_API_TOKEN")

    if not dt_api_url:
        raise ValueError(
            "DT_API_URL not found in environment variables. "
            "Please set it in your .env file."
        )
    if not dt_api_token:
        raise ValueError(
            "DT_API_TOKEN not found in environment variables. "
            "Please set it in your .env file."
        )

    base_otlp_endpoint = dt_api_url.rstrip("/")

    resource = Resource.create({"service.name": service_name})

    exporter = OTLPSpanExporter(
        endpoint=f"{base_otlp_endpoint}/v1/traces",
        headers={"Authorization": f"Api-Token {dt_api_token}"},
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if Traceloop is not None:
        Traceloop.init(
            app_name=service_name,
            api_endpoint=base_otlp_endpoint,
            headers={"Authorization": f"Api-Token {dt_api_token}"},
            disable_batch=True,
        )
        logger.info("Traceloop initialized for AI observability")
    else:
        logger.warning(
            "traceloop-sdk is not installed; continuing with standard "
            "OpenTelemetry tracing only"
        )

    _TRACING_INITIALIZED = True
