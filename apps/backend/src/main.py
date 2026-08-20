"""
CollabSpace — FastAPI application entry point.

Startup sequence:
  1. Connect Prisma (PostgreSQL)
  2. Connect Redis
  3. Mount routers
  4. Serve

Shutdown sequence:
  1. Close Redis
  2. Disconnect Prisma
"""

import logging
from contextlib import asynccontextmanager

import asyncio
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.config import settings
from src.database import connect_db, disconnect_db
from src.redis_client import close_redis, init_redis
from src.workspaces.router import router as workspaces_router
from src.realtime.router import router as realtime_router
from src.realtime.manager import manager
from src.documents.router import router as documents_router
from src.chat.router import router as chat_router
from src.notifications.router import router as notifications_router
from src.notifications.service import worker as notification_worker
from src.ai.router import router as ai_router
from src.metrics import router as metrics_router
from src.middleware.rate_limit import RateLimitMiddleware

# Configure structlog for JSON production logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting CollabSpace API", env=settings.app_env)
    await connect_db()
    log.info("Prisma connected")
    await init_redis()
    log.info("Redis connected")
    
    # Start Redis Pub/Sub listener for WebSockets
    manager.pubsub_task = asyncio.create_task(manager.start_redis_listener())
    
    # Start presence monitor
    manager.presence_monitor_task = asyncio.create_task(manager.start_presence_monitor())
    
    # Start notification worker (consumes Redis queue, writes to Postgres, pushes WS)
    notification_worker.start()
    
    yield
    
    log.info("Shutting down")
    if manager.pubsub_task:
        manager.pubsub_task.cancel()
        try:
            await manager.pubsub_task
        except asyncio.CancelledError:
            pass
            
    if manager.presence_monitor_task:
        manager.presence_monitor_task.cancel()
        try:
            await manager.presence_monitor_task
        except asyncio.CancelledError:
            pass
            
    # Stop notification worker
    notification_worker.stop()
            
    await close_redis()
    await disconnect_db()


app = FastAPI(
    title="CollabSpace API",
    description=(
        "Google Docs + Slack + AI collaboration platform. "
        "Built for SDE placement portfolio."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,   # required for httpOnly cookie on cross-origin requests
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rate Limiting (global sliding-window, per-route tiers) ───────────────────
app.add_middleware(RateLimitMiddleware)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(workspaces_router, prefix="/workspaces", tags=["Workspaces"])
app.include_router(realtime_router, prefix="/realtime", tags=["Realtime"])
app.include_router(documents_router, prefix="/documents", tags=["Documents"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
app.include_router(ai_router, prefix="/ai", tags=["AI"])
app.include_router(metrics_router)


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/ready", tags=["Health"], summary="Readiness probe")
async def readiness_check():
    # Both DB and Redis are connected during lifespan — if we're here, we're ready
    return {"status": "ready", "db": "connected", "redis": "connected"}
