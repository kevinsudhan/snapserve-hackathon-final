"""Claims: list, detail, reviewer patch, evidence link."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db import ClaimRow, now_iso, read_session, session_scope
from app.events import emit
from app.schemas import Claim, ClaimPatch, EvidenceLinkResponse
from app.serializers import claim_summary, claim_to_schema
from services import evidence as evidence_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["claims"])


def _matches_query(row: ClaimRow, needle: str) -> bool:
    haystack = " ".join(
        str(part or "")
        for part in (
            row.reference,
            row.crop,
            row.damage_type,
            row.narrative,
            (row.farmer or {}).get("name"),
            (row.farmer or {}).get("phone"),
            (row.location or {}).get("village"),
            (row.location or {}).get("taluk"),
            (row.location or {}).get("district"),
        )
    ).lower()
    return needle in haystack


@router.get("/claims", response_model=list[Claim])
async def list_claims(
    status: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> list[Claim]:
    """Newest first. Daily weather series is trimmed here; the detail view has it."""
    needle = (q or "").strip().lower()
    with read_session() as session:
        statement = select(ClaimRow).order_by(ClaimRow.id.desc())
        if status:
            statement = statement.where(ClaimRow.status == status)
        rows = session.scalars(statement.limit(limit)).all()
        claims = [
            claim_to_schema(session, row)
            for row in rows
            if not needle or _matches_query(row, needle)
        ]
    for claim in claims:
        pass  # daily series kept: the Live Desk renders the chart from the list payload
    return claims


@router.get("/claims/{claim_id}", response_model=Claim)
async def get_claim(claim_id: int) -> Claim:
    with read_session() as session:
        row = session.get(ClaimRow, claim_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        return claim_to_schema(session, row)


@router.patch("/claims/{claim_id}", response_model=Claim)
async def patch_claim(claim_id: int, patch: ClaimPatch) -> Claim:
    with session_scope() as session:
        row = session.get(ClaimRow, claim_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if patch.status is not None:
            row.status = patch.status
        if patch.reviewer_notes is not None:
            row.reviewer_notes = patch.reviewer_notes
        row.updated_at = now_iso()
        session.flush()
        claim = claim_to_schema(session, row)

    payload = claim_summary(claim)
    payload["stage"] = "reviewer"
    await emit("claim.updated", payload)
    logger.info("claim %s updated by reviewer", claim.reference)
    return claim


@router.post("/claims/{claim_id}/evidence-link", response_model=EvidenceLinkResponse)
async def create_evidence_link(claim_id: int) -> EvidenceLinkResponse:
    try:
        return evidence_service.create_link(claim_id)
    except evidence_service.EvidenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
