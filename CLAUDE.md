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

### Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API authentication |
| `OPENAI_MODEL` | No | `gpt-3.5-turbo` | Model for LLM synthesis |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `DT_API_URL` | No* | — | Dynatrace OTLP base endpoint (no trailing slash) |
| `DT_API_TOKEN` | No* | — | Dynatrace API token (`openTelemetryTrace.ingest` + `metrics.ingest` scopes) |

*Missing `DT_*` vars trigger a warning at startup; the app continues without telemetry.

### Local Python (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env  # set OPENAI_API_KEY
uvicorn app:app --host 0.0.0.0 --port 8000
```

CLI mode (interactive REPL, no HTTP server):

```bash
RUN_MODE=cli python research_assistant.py
```

## Known Issues

**docker-compose 1.29.2 `ContainerConfig` crash** — when trying to recreate a container built from a newer image format, docker-compose 1.29.2 throws `KeyError: 'ContainerConfig'`. Workaround: remove the container by ID or name first, then run `docker-compose up`:

```bash
docker stop research-assistant && docker rm research-assistant
docker-compose up -d research-assistant
```

If the container no longer exists (already removed by a failed recreate), skip the first command. If docker rm fails with a hash-named container (e.g. `dcdf01325951_research-assistant`), use that full name in the `docker rm` command.

**Trace linking: OneAgent HTTP spans and Traceloop LangChain spans remain in separate traces** — OneAgent (via nginx) and Traceloop use independent `TracerProvider` instances that do not share trace context. Even though W3C `traceparent` headers are propagated from nginx → FastAPI, Traceloop does not use this as a parent context when initializing its root span. The result: HTTP requests appear as one trace (nginx → FastAPI), while LangChain work appears as a separate trace.

Workaround implemented: `_parse_traceparent_to_link()` in `research_assistant.py` parses the W3C `traceparent` header forwarded by nginx into an OTel `Link` object. `handle_research_query()` passes this link when starting the `research_assistant.query` span, so Dynatrace can correlate the two traces even though they are not in a parent–child relationship. Both traces are valid and exportable; they are linked but not merged into a single end-to-end trace.

## Architecture

**`app.py`** — FastAPI service. Handles HTTP requests, session management, and request logging with trace context. On startup, calls `setup_tracing()` from `research_assistant.py`, then starts a background session cleanup task. Serves the web UI from `public/` via a `StaticFiles` mount at `/` (added last so API routes take precedence). Offloads synchronous LangChain calls to a thread pool via `asyncio.to_thread`. Uses per-session `asyncio.Lock` to serialize concurrent requests to the same session's shared memory.

**`research_assistant.py`** — LangChain agent. Imports `tracing.py` at the top (before any LangChain components are instantiated) so Traceloop can patch LangChain at import time. Initialises a `CHAT_CONVERSATIONAL_REACT_DESCRIPTION` agent with a single `wikipedia_search` tool and `ConversationBufferMemory`. The agent autonomously decides when and what to search. Key functions:
- `create_agent_for_session()` — returns `(agent, memory)` tuple; called by `app.py` when a new HTTP session is created
- `run_agent_query()` — decorated `@task`, invokes `agent.run(query)`
- `handle_research_query()` — decorated `@workflow`, creates a manual OTel span (`research_assistant.query`) with `research.query` and `research.model` attributes, attaches an OTel `Link` to the HTTP parent span if `parent_traceparent` is provided
- `_parse_traceparent_to_link()` — parses W3C `traceparent` header (version-trace_id-parent_id-flags) into an OTel `Link`; returns `None` on any parse failure
- `run_research_assistant()` — interactive CLI loop (used when `RUN_MODE=cli`)

The `@workflow`, `@task`, and `@tool` decorators from `traceloop-sdk` fall back to identity decorators (no-ops) if the SDK is absent.

**`tracing.py`** — Sets global W3C trace context + Jaeger baggage propagators at module load time (before `setup_tracing()` is called). `setup_tracing(service_name)` raises `ValueError` if `DT_*` env vars are missing. When Traceloop is available, calls `Traceloop.init(app_name=, api_endpoint=, headers=)` — Traceloop then owns both the `TracerProvider` and `MeterProvider`. The fallback path (Traceloop absent) manually configures a `TracerProvider` only — no metrics pipeline. A `_TRACING_INITIALIZED` guard prevents double-init. `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` is set via `os.environ.setdefault()` before `Traceloop.init()` so Traceloop's internally created `OTLPMetricExporter` also picks it up.

**`public/`** — static web UI (HTML/CSS/JS). Served directly by FastAPI in development and Docker deployments. Uses `localStorage` for session persistence and calls `/api/chat` and `/api/chat/history`. Enter submits; Shift+Enter allows multiline input.

**`nginx.conf`** — optional nginx configuration for production deployments requiring port 80, a custom domain, or HTTPS. When nginx is in front, it proxies `/api/` and `/health` to the FastAPI container on port 8000. Critically, it forwards `traceparent` and `tracestate` headers to the upstream so OTel trace context propagates from OneAgent through to the application.

## API Reference

### `POST /api/chat`

Submit a research query. Creates a new session if `session_id` is absent.

Request body (`ChatRequest`):
```json
{ "message": "What is quantum entanglement?", "session_id": "optional-uuid" }
```

Response (`ChatResponse`):
```json
{ "session_id": "uuid", "response": "...", "status": "ok" }
```

### `GET /api/chat/history?session_id=<uuid>`

Returns the full conversation history for a session. Returns 404 if the session does not exist.

Response (`HistoryResponse`):
```json
{ "session_id": "uuid", "history": [{ "role": "user", "content": "..." }, ...] }
```

### `GET /health`

Liveness probe. Returns 200 with `{ "status": "ok", "sessions_active": N }`.

## Session Management

- Sessions are keyed by a UUID generated in the browser and persisted to `localStorage`.
- Each session stores: `agent`, `memory`, `lock` (`asyncio.Lock`), `last_accessed` (epoch), `request_count`.
- Concurrent requests to the same session are serialized by the per-session lock.
- A background task (`cleanup_sessions`) runs every 5 minutes and removes sessions idle for more than 24 hours.
- Tracing disabled or startup errors do not prevent session creation — the app degrades gracefully.

## Key Design Constraints

- The agent uses Wikipedia as its only tool by design. Adding general web search would significantly change scope and cost.
- `ConversationBufferMemory` persists the full chat history for the entire session. Long sessions will eventually hit the context window limit of the configured model.
- `tracing.py` must be imported before LangChain components are initialised because Traceloop patches LangChain at import time. This ordering is enforced by the import at the top of `research_assistant.py`.
- `DT_API_URL` must be the base Dynatrace OTLP endpoint (e.g. `https://<env>.live.dynatrace.com/api/v2/otlp`) with no trailing slash. `tracing.py` appends `/v1/traces` and `/v1/metrics` for the respective exporters.
- `Traceloop.init()` is called with `api_endpoint=` (not `exporter=`). Passing `exporter=` without `api_endpoint=` causes Traceloop to print "Metrics are disabled" and skip its entire metrics instrumentation pipeline.
- `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` is set via `os.environ.setdefault()` before `Traceloop.init()`. Dynatrace rejects `CUMULATIVE` monotonic sums (`UNSUPPORTED_METRIC_TYPE_MONOTONIC_CUMULATIVE_SUM`); the OTel HTTP exporter defaults to `CUMULATIVE`. The `preferred_temporality` constructor argument is not used because the SDK validates its keys against internal class references that differ from the public API classes.
- CORS middleware sets `allow_credentials=False` when `allow_origins=["*"]` — the CORS spec forbids the combination of wildcard origins with credentials. In production, nginx serves the frontend on the same origin so CORS is not exercised.
- `app.py` imports `research_assistant` lazily (inside request handlers) rather than at module top-level. This prevents LangChain from being initialised before tracing is set up.

## Telemetry Span Inventory

| Span name | Source | Key attributes |
|---|---|---|
| `research_assistant.query` | `handle_research_query()` manual span | `research.query`, `research.model`, `research.result_length` |
| `wikipedia.search` | `wikipedia_search()` manual span | `wikipedia.query`, `wikipedia.result_length`, `wikipedia.disambiguation` |
| LangChain agent spans | Traceloop auto-instrumentation | LangChain internals |
| OpenAI LLM spans | Traceloop auto-instrumentation | token counts, model, latency |

## Dependency Versions (requirements.txt)

| Package | Version |
|---|---|
| `langchain` | 0.2.0 |
| `langchain-openai` | 0.1.22 |
| `langchain-community` | 0.2.0 |
| `openai` | >=1.40.0,<2.0.0 |
| `wikipedia` | 1.4.0 |
| `python-dotenv` | 1.0.0 |
| `opentelemetry-sdk` | >=1.42.0,<2.0.0 |
| `opentelemetry-exporter-otlp-proto-http` | >=1.42.0,<2.0.0 |
| `traceloop-sdk` | >=0.40.4,<1.0.0 |
| `fastapi` | 0.104.1 |
| `uvicorn[standard]` | 0.24.0 |
| `pydantic` | 2.5.0 |
| `python-json-logger` | 2.0.7 |
| `aiofiles` | >=23.1.0 |

Pinned versions ensure Traceloop's LangChain patches are compatible. Do not upgrade `langchain*` or `traceloop-sdk` independently.
