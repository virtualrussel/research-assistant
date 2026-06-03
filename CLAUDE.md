# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This is a practice project for learning how to instrument a Python front-end that uses LangChain and OpenAI. The research assistant application itself is the vehicle — the real focus is on getting OpenTelemetry (manual spans) and OpenLLMetry/Traceloop (automatic LangChain/LLM instrumentation) data flowing correctly into Dynatrace. Work here should prioritise correct, observable instrumentation over extending the assistant's research capabilities.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # then populate OPENAI_API_KEY at minimum
python research_assistant.py
```

Required env var: `OPENAI_API_KEY`. Optional: `OPENAI_MODEL` (default `gpt-3.5-turbo`), `LOG_LEVEL`. For Dynatrace observability: `DT_API_URL` (base OTLP endpoint, no trailing slash) and `DT_API_TOKEN` (must have both `openTelemetryTrace.ingest` and `metrics.ingest` scopes).

There is no build step, no test suite, and no linter config. The devcontainer uses `black` for formatting.

## Architecture

The project has two modules:

**`tracing.py`** — sets `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` then calls `Traceloop.init()` with `api_endpoint=`. Traceloop owns both the `TracerProvider` and `MeterProvider`; the OTel SDK prevents overriding the `MeterProvider` once set, so the metrics pipeline belongs entirely to Traceloop. The DELTA env var must be set before `Traceloop.init()` so Traceloop's internally created `OTLPMetricExporter` also picks it up. If `DT_*` env vars are missing, `setup_tracing()` raises `ValueError`. The fallback path (no Traceloop) manually configures a `TracerProvider` only — no metrics pipeline.

**`research_assistant.py`** — initializes a LangChain `CHAT_CONVERSATIONAL_REACT_DESCRIPTION` agent with a single `wikipedia_search` tool and `ConversationBufferMemory`. The agent autonomously decides when and what to search. Two instrumented entry points wrap queries:
- `run_agent_query()` — decorated `@task`, handles the direct agent invocation
- `handle_research_query()` — decorated `@workflow`, wraps the full query lifecycle including a manual span with query/result attributes

The `@workflow`, `@task`, and `@tool` decorators from `traceloop-sdk` become no-ops if the SDK is absent.

## Key Design Constraints

- The agent uses Wikipedia as its only tool by design. Adding general web search would significantly change scope and cost.
- `ConversationBufferMemory` persists the full chat history for the entire session. Long sessions will eventually hit the context window limit of the configured model.
- `tracing.py` must be imported before LangChain components are initialised because Traceloop patches LangChain at import time. This ordering is enforced by the import at the top of `research_assistant.py`.
- `DT_API_URL` must be the base Dynatrace OTLP endpoint (e.g. `https://<env>.live.dynatrace.com/api/v2/otlp`) with no trailing slash. `tracing.py` appends `/v1/traces` and `/v1/metrics` for the respective exporters.
- `Traceloop.init()` is called with `api_endpoint=` (not `exporter=`). Passing `exporter=` without `api_endpoint=` causes Traceloop to print "Metrics are disabled" and skip its entire metrics instrumentation pipeline.
- `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` is set via `os.environ.setdefault()` before `Traceloop.init()`. Dynatrace rejects `CUMULATIVE` monotonic sums (`UNSUPPORTED_METRIC_TYPE_MONOTONIC_CUMULATIVE_SUM`); the OTel HTTP exporter defaults to `CUMULATIVE`. The env var is set before `Traceloop.init()` so Traceloop's internally created `OTLPMetricExporter` also picks it up. The `preferred_temporality` constructor argument is not used because the SDK validates its keys against internal class references that differ from the public API classes.
