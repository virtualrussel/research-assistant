# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

A research assistant web application backed by LangChain, OpenAI, and Wikipedia. The assistant takes research questions via a browser UI, autonomously searches Wikipedia, and synthesizes findings into comprehensive responses using OpenAI.

OpenTelemetry (manual spans) and OpenLLMetry/Traceloop (automatic LangChain and LLM instrumentation) are baked in throughout. The primary deliverable is a functional, working assistant. Getting telemetry flowing correctly to Dynatrace is part of the project but not at the expense of the assistant itself.

## Setup

```bash
cp .env.example .env  # populate OPENAI_API_KEY at minimum
docker-compose up -d research-assistant
# UI available at http://localhost:8000
```

Required env var: `OPENAI_API_KEY`. Optional: `OPENAI_MODEL` (default `gpt-3.5-turbo`), `LOG_LEVEL`. For Dynatrace observability: `DT_API_URL` (base OTLP endpoint, no trailing slash) and `DT_API_TOKEN` (must have both `openTelemetryTrace.ingest` and `metrics.ingest` scopes).

There is no build step, no test suite, and no linter config. The devcontainer uses `black` for formatting.

## Known Issues

**docker-compose 1.29.2 `ContainerConfig` crash** — when trying to recreate a container built from a newer image format, docker-compose 1.29.2 throws `KeyError: 'ContainerConfig'`. Workaround: remove the container by ID or name first, then run `docker-compose up`:

```bash
docker stop research-assistant && docker rm research-assistant
docker-compose up -d research-assistant
```

If the container no longer exists (already removed by a failed recreate), skip the first command. If docker rm fails with a hash-named container (e.g. `dcdf01325951_research-assistant`), use that full name in the `docker rm` command.

**Trace linking: OneAgent HTTP spans and Traceloop LangChain spans remain separate** — OneAgent (via nginx) and Traceloop use independent `TracerProvider` instances that do not share trace context. Even though W3C `traceparent` headers are propagated from nginx → FastAPI, Traceloop does not read this context when initializing its root span. The result: HTTP requests appear as one trace (nginx → FastAPI), while LangChain work appears as a separate, unlinked trace. Both traces are valid and exportable to Dynatrace, but they cannot be traversed as a single end-to-end flow. Root cause: Traceloop initializes its `TracerProvider` at application startup, before the first request, and does not accept a parent context parameter. Workaround: none implemented. Future: would require either Traceloop API changes to accept parent context at init time, or a custom span link mechanism between the two traces.

## Architecture

**`app.py`** — FastAPI service. Handles HTTP requests, session management, and request logging with trace context. On startup, initialises tracing then starts a background session cleanup task. Serves the web UI from `public/` via a StaticFiles mount at `/` (added last so API routes take precedence). Offloads synchronous LangChain calls to a thread pool via `asyncio.to_thread`.

**`research_assistant.py`** — LangChain agent. Initialises a `CHAT_CONVERSATIONAL_REACT_DESCRIPTION` agent with a single `wikipedia_search` tool and `ConversationBufferMemory`. The agent autonomously decides when and what to search. Two instrumented entry points wrap queries:
- `run_agent_query()` — decorated `@task`, handles the direct agent invocation
- `handle_research_query()` — decorated `@workflow`, wraps the full query lifecycle including a manual span with query/result attributes

The `@workflow`, `@task`, and `@tool` decorators from `traceloop-sdk` become no-ops if the SDK is absent.

**`tracing.py`** — sets `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` then calls `Traceloop.init()` with `api_endpoint=`. Traceloop owns both the `TracerProvider` and `MeterProvider`; the OTel SDK prevents overriding the `MeterProvider` once set, so the metrics pipeline belongs entirely to Traceloop. The DELTA env var must be set before `Traceloop.init()` so Traceloop's internally created `OTLPMetricExporter` also picks it up. If `DT_*` env vars are missing, `setup_tracing()` raises `ValueError`. The fallback path (no Traceloop) manually configures a `TracerProvider` only — no metrics pipeline.

**`public/`** — static web UI (HTML/CSS/JS). Served directly by FastAPI in development and Docker deployments. Uses `localStorage` for session persistence and calls `/api/chat` and `/api/chat/history`.

**`nginx.conf`** — optional nginx configuration for production deployments requiring port 80, a custom domain, or HTTPS. When nginx is in front, it proxies `/api/` and `/health` to the FastAPI container on port 8000 and can serve `public/` directly.

## Key Design Constraints

- The agent uses Wikipedia as its only tool by design. Adding general web search would significantly change scope and cost.
- `ConversationBufferMemory` persists the full chat history for the entire session. Long sessions will eventually hit the context window limit of the configured model.
- `tracing.py` must be imported before LangChain components are initialised because Traceloop patches LangChain at import time. This ordering is enforced by the import at the top of `research_assistant.py`.
- `DT_API_URL` must be the base Dynatrace OTLP endpoint (e.g. `https://<env>.live.dynatrace.com/api/v2/otlp`) with no trailing slash. `tracing.py` appends `/v1/traces` and `/v1/metrics` for the respective exporters.
- `Traceloop.init()` is called with `api_endpoint=` (not `exporter=`). Passing `exporter=` without `api_endpoint=` causes Traceloop to print "Metrics are disabled" and skip its entire metrics instrumentation pipeline.
- `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` is set via `os.environ.setdefault()` before `Traceloop.init()`. Dynatrace rejects `CUMULATIVE` monotonic sums (`UNSUPPORTED_METRIC_TYPE_MONOTONIC_CUMULATIVE_SUM`); the OTel HTTP exporter defaults to `CUMULATIVE`. The env var is set before `Traceloop.init()` so Traceloop's internally created `OTLPMetricExporter` also picks it up. The `preferred_temporality` constructor argument is not used because the SDK validates its keys against internal class references that differ from the public API classes.
