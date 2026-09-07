"""GET /api/health"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app import __version__, providers
from app.config import settings
from app.schemas import HealthResponse
from services import gemini
from services.poller import poller_status
from services.snapserve import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness plus the state of each external dependency."""
    return HealthResponse(
        ok=True,
        version=__version__,
        snapserve_ok=get_client().configured,
        gemini_ok=gemini.is_available(),
        poller=poller_status(),
        data_down_mode=settings.data_down_mode,
    )


@router.get("/health/modules")
async def module_health() -> dict:
    """Which sibling service modules are importable (data/schemes workers)."""
    return {"modules": providers.module_status()}
