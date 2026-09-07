"""Admin/demo controls: simulate a call, toggle data-down, reset the demo."""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter
from sqlalchemy import delete

from app.config import settings
from app.db import (
    CallRow,
    ClaimRow,
    EvidenceFileRow,
    EvidenceTokenRow,
    GuardrailIncidentRow,
    TicketRow,
    meta_set,
    now_iso,
    session_scope,
)
from app.events import emit
from app.schemas import CallRecord, DataDownRequest, SimulateRequest
from services import ingest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

RESET_KEY = "poller.reset_at"


@router.post("/simulate", response_model=CallRecord)
async def simulate(request: SimulateRequest) -> CallRecord:
    """Run the full ingest pipeline over a pasted transcript."""
    logger.info("simulating a call (%d chars)", len(request.transcript or ""))
    return await ingest.simulate(
        transcript=request.transcript,
        from_number=request.from_number,
        language=request.language,
    )


@router.post("/data-down")
async def data_down(request: DataDownRequest) -> dict:
    """Force every data check to report ``unverifiable`` (failure drill)."""
    settings.data_down_mode = request.enabled
    logger.info("data-down mode %s", "ON" if request.enabled else "OFF")
    await emit("poller.status", {"data_down_mode": request.enabled})
    return {"enabled": request.enabled}


@router.post("/reset-demo")
async def reset_demo() -> dict:
    """Clear calls, claims, tickets and evidence. Knowledge is untouched."""
    with session_scope() as session:
        counts = {
            "calls": session.query(CallRow).count(),
            "claims": session.query(ClaimRow).count(),
            "tickets": session.query(TicketRow).count(),
            "evidence_files": session.query(EvidenceFileRow).count(),
        }
        for model in (
            GuardrailIncidentRow,
            EvidenceFileRow,
            EvidenceTokenRow,
            TicketRow,
            ClaimRow,
            CallRow,
        ):
            session.execute(delete(model))

    if settings.evidence_dir.exists():
        for child in settings.evidence_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    # Stop the poller from re-ingesting the calls we just cleared.
    meta_set(RESET_KEY, now_iso())
    logger.info("demo reset: %s", counts)
    await emit("poller.status", {"reset": True, "cleared": counts})
    return {"cleared": counts}
