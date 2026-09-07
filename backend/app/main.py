"""FastAPI application entry point.

Run from ``backend/``::

    .venv\\Scripts\\python -m uvicorn app.main:app --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.db import init_db
from app.events import broadcaster
from app.routers import (
    admin,
    calls,
    citations,
    claims,
    evaluation,
    evidence,
    health,
    knowledge,
    stats,
    tickets,
    ws,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("fasaldesk")

# Dashboard on localhost plus anything on the LAN (farmers scan the QR from a phone).
LAN_ORIGIN_REGEX = (
    r"https?://(localhost|127\.0\.0\.1|(\d{1,3}\.){3}\d{1,3}|[\w.-]+\.local)(:\d+)?"
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    broadcaster.bind_loop(asyncio.get_running_loop())

    poller = None
    if settings.poller_enabled:
        from services.poller import get_poller

        poller = get_poller()
        if poller.client.configured:
            await poller.start()
        else:
            logger.warning("SNAPSERVE_API_KEY not set — poller idle")
    else:
        logger.info("poller disabled by configuration")

    logger.info(
        "FasalDesk backend %s ready (agent %s, data_down=%s)",
        __version__,
        settings.snapserve_agent_id,
        settings.data_down_mode,
    )
    try:
        yield
    finally:
        if poller is not None:
            await poller.stop()


app = FastAPI(
    title="FasalDesk backend",
    version=__version__,
    description="Voice claims desk for farmers — call ingest, truth-check, CRM API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_origin, "http://localhost:5173", "*"],
    allow_origin_regex=LAN_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    health,
    stats,
    calls,
    claims,
    tickets,
    evidence,
    knowledge,
    citations,
    admin,
    evaluation,
    ws,
):
    app.include_router(module.router)

# Convenience: raw evidence files also served statically.
settings.ensure_dirs()
app.mount(
    "/static/evidence",
    StaticFiles(directory=str(settings.evidence_dir), check_dir=False),
    name="evidence-static",
)


@app.get("/", tags=["health"])
async def root() -> dict:
    return {
        "name": "FasalDesk backend",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
        "events": "/ws/events",
    }


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", exc.__class__.__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error", "error": exc.__class__.__name__},
    )
