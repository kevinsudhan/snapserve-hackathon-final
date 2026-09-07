"""Eval endpoints.

The red-team harness is a later worker's job; the shapes and routes are fixed
here so the dashboard can build against them.  ``latest`` returns whatever run
has been stored (``null`` until one exists) and ``run`` answers 501.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db import EvalRunRow, read_session
from app.schemas import EvalReport, EvalRunRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.get("/latest", response_model=EvalReport | None)
async def latest() -> EvalReport | None:
    with read_session() as session:
        row = session.scalars(
            select(EvalRunRow).order_by(EvalRunRow.started_at.desc()).limit(1)
        ).first()
    if row is None or not row.data:
        return None
    try:
        return EvalReport.model_validate(row.data)
    except Exception:
        logger.warning("stored eval run %s is not a valid EvalReport", row.run_id)
        return None


@router.post("/run", status_code=501)
async def run(request: EvalRunRequest) -> dict:
    raise HTTPException(
        status_code=501,
        detail="The red-team eval harness is not wired up yet.",
    )
