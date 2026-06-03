"""
FastAPI HTTP service for the Research Assistant.

Provides REST API endpoints for chatting with the research assistant,
managing sessions, and health monitoring.
"""

import asyncio
import logging
import logging.handlers
import os
import time
from queue import Queue
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pythonjsonlogger import jsonlogger
from opentelemetry import trace

# ============================================================================
# Logging Configuration
# ============================================================================

# Suppress noisy loggers
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Queue-based logging for async safety
log_queue = Queue()
queue_handler = logging.handlers.QueueHandler(log_queue)
queue_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt='%(timestamp)s %(level)s %(name)s %(message)s',
        timestamp=True
    )
)

root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(queue_handler)
root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Start queue listener thread (writes to stdout)
queue_listener = logging.handlers.QueueListener(
    log_queue,
    logging.StreamHandler(),
    respect_handler_level=True
)
queue_listener.start()

logger = logging.getLogger(__name__)

# ============================================================================
# Pydantic Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="User query")
    session_id: Optional[str] = Field(None, description="Existing session ID (optional)")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    status: str = "ok"


class HistoryMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    history: List[HistoryMessage]


class HealthResponse(BaseModel):
    status: str
    sessions_active: int


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Research Assistant",
    version="1.0.0",
    description="AI-powered research assistant with Wikipedia search and OpenAI integration"
)

# CORS middleware for local development; in production Nginx serves frontend
# on same origin so CORS is not exercised. allow_credentials must be False
# when allow_origins=["*"] — the CORS spec forbids the combination.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ============================================================================
# Session Management
# ============================================================================

sessions: Dict[str, dict] = {}
active_requests: int = 0  # count of requests currently being processed
SHUTDOWN_TIMEOUT = 30  # seconds to wait for in-flight requests


async def cleanup_sessions():
    """Background task: remove expired sessions every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        now = time.time()
        expired = [sid for sid, data in sessions.items()
                   if now - data["last_accessed"] > 86400]  # 24 hours

        if expired:
            logger.info(
                "Session cleanup task executed",
                extra={
                    "checked_sessions": len(sessions),
                    "expired_count": len(expired),
                }
            )

            for sid in expired:
                logger.info(
                    "Session expired and removed",
                    extra={"session_id": sid}
                )
                del sessions[sid]


# ============================================================================
# Startup & Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize tracing and background tasks on application startup."""
    logger.info("Application startup sequence initiated")

    try:
        from research_assistant import setup_tracing
        setup_tracing(service_name="research-assistant-api")
        logger.info("Dynatrace OpenTelemetry tracing initialized")
    except ValueError as e:
        logger.warning(f"Tracing not configured: {e}. Continuing without Dynatrace.")
    except Exception as e:
        logger.error(f"Error initializing tracing: {e}", exc_info=True)
        # Don't fail startup; continue without tracing

    # Start cleanup task
    asyncio.create_task(cleanup_sessions())
    logger.info("Session cleanup background task started")
    logger.info("Application startup complete; ready for requests")


@app.on_event("shutdown")
async def shutdown():
    """Graceful shutdown: wait for in-flight requests to complete."""
    global active_requests
    logger.info(f"Shutdown signal received; waiting up to {SHUTDOWN_TIMEOUT}s for in-flight requests")

    start = time.time()
    while active_requests > 0 and (time.time() - start) < SHUTDOWN_TIMEOUT:
        await asyncio.sleep(0.1)

    if active_requests > 0:
        logger.warning(f"Shutdown timeout; {active_requests} requests still in-flight")

    logger.info("Application shutdown complete")


# ============================================================================
# Middleware
# ============================================================================

@app.middleware("http")
async def log_request_context(request: Request, call_next):
    """Log HTTP request/response with trace context; track in-flight count."""
    global active_requests
    request.state.session_id = None
    request.state.start_time = time.time()
    request.state.request_id = str(uuid4())

    active_requests += 1
    try:
        logger.info(
            "HTTP request received",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            }
        )

        response = await call_next(request)

        # Extract trace context after handler runs (Traceloop instrumented by now)
        span = trace.get_current_span()
        span_ctx = span.get_span_context() if span else None

        duration_ms = (time.time() - request.state.start_time) * 1000
        logger.info(
            "HTTP response sent",
            extra={
                "request_id": request.state.request_id,
                "session_id": getattr(request.state, "session_id", None),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "trace_id": str(span_ctx.trace_id) if span_ctx else None,
                "span_id": str(span_ctx.span_id) if span_ctx else None,
            }
        )

        return response
    except Exception as e:
        logger.error(
            "Exception in request handler",
            extra={
                "request_id": request.state.request_id,
                "session_id": getattr(request.state, "session_id", None),
                "error": str(e),
            },
            exc_info=True
        )
        raise
    finally:
        active_requests -= 1


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, request_body: ChatRequest):
    """Handle chat message; create or reuse session."""
    session_id = request_body.session_id or str(uuid4())

    # Set session_id as span attribute for Dynatrace correlation
    span = trace.get_current_span()
    span.set_attribute("session_id", session_id)

    # Get or create session
    if session_id not in sessions:
        logger.debug(
            "Creating new session",
            extra={"session_id": session_id}
        )

        try:
            from research_assistant import create_agent_for_session
            agent, memory = create_agent_for_session()
            sessions[session_id] = {
                "agent": agent,
                "memory": memory,
                "lock": asyncio.Lock(),
                "last_accessed": time.time(),
                "request_count": 0,
            }
        except Exception as e:
            logger.error(
                "Failed to initialize agent for session",
                extra={"session_id": session_id, "error": str(e)},
                exc_info=True
            )
            raise HTTPException(status_code=500, detail=str(e))
    else:
        logger.debug(
            "Using existing session",
            extra={"session_id": session_id}
        )

    # Check session still exists (in case cleanup ran)
    if session_id not in sessions:
        logger.warning(
            "Session not found during request",
            extra={"session_id": session_id}
        )
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    session["last_accessed"] = time.time()
    session["request_count"] += 1

    # Expose session_id to request middleware for logging
    request.state.session_id = session_id

    # Serialize access to memory via lock
    async with session["lock"]:
        try:
            from research_assistant import handle_research_query

            logger.debug(
                "Executing query",
                extra={
                    "session_id": session_id,
                    "query_length": len(request_body.message),
                }
            )

            # handle_research_query is synchronous (LangChain/OpenAI); offload
            # to a thread so the event loop remains free for other requests.
            result = await asyncio.to_thread(
                handle_research_query,
                session["agent"],
                request_body.message,
            )

            logger.debug(
                "Query executed successfully",
                extra={
                    "session_id": session_id,
                    "response_length": len(result),
                }
            )

            return ChatResponse(
                session_id=session_id,
                response=result,
                status="ok"
            )

        except Exception as e:
            logger.error(
                "Error executing query",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                },
                exc_info=True
            )
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history", response_model=HistoryResponse)
async def history(session_id: str):
    """Return conversation history for session."""
    if session_id not in sessions:
        logger.warning(
            "History requested for non-existent session",
            extra={"session_id": session_id}
        )
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        memory = sessions[session_id]["memory"]
        memory_vars = memory.load_memory_variables({})

        # Convert memory format to response format
        messages = []
        if "chat_history" in memory_vars:
            for msg in memory_vars["chat_history"]:
                messages.append(HistoryMessage(
                    role="user" if msg.type == "human" else "assistant",
                    content=msg.content
                ))

        logger.debug(
            "History retrieved",
            extra={
                "session_id": session_id,
                "message_count": len(messages),
            }
        )

        return HistoryResponse(
            session_id=session_id,
            history=messages
        )
    except Exception as e:
        logger.error(
            "Error retrieving history",
            extra={"session_id": session_id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    """Liveness probe for load balancer/monitoring."""
    return HealthResponse(status="ok", sessions_active=len(sessions))


# ============================================================================
# Root Endpoint (Redirect to Docs)
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint; redirect to API documentation."""
    return {
        "message": "Research Assistant API",
        "docs": "/docs",
        "openapi": "/openapi.json"
    }
