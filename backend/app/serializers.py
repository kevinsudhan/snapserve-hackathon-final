"""DB row -> pydantic conversions used by the routers and the pipeline."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import CallRow, ClaimRow, EvidenceFileRow, TicketRow
from app.schemas import (
    CallRecord,
    Claim,
    EvidenceFile,
    GuardrailIncident,
    Ticket,
    coerce,
    coerce_list,
)


def evidence_file_url(file_id: str) -> str:
    return f"/api/evidence/files/{file_id}"


def evidence_file_to_schema(row: EvidenceFileRow) -> EvidenceFile:
    return EvidenceFile(
        id=row.id,
        item_key=row.item_key,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        uploaded_at=row.uploaded_at,
        client_time=row.client_time,
        lat=row.lat,
        lon=row.lon,
        url=evidence_file_url(row.id),
        quality_flag=row.quality_flag,  # type: ignore[arg-type]
    )


def call_to_schema(row: CallRow) -> CallRecord:
    return CallRecord.model_validate(
        {
            "id": row.id,
            "snapserve_call_id": row.snapserve_call_id,
            "direction": row.direction,
            "from_number": row.from_number,
            "to_number": row.to_number,
            "status": row.status,
            "started_at": row.started_at,
            "ended_at": row.ended_at,
            "duration_seconds": row.duration_seconds,
            "language_detected": row.language_detected,
            "languages": row.languages or [],
            "code_switching": bool(row.code_switching),
            "transcript": row.transcript or [],
            "summary": row.summary,
            "recording_url": row.recording_url,
            "claim_id": row.claim_id,
            "ticket_id": row.ticket_id,
            "guardrail_incidents": row.guardrail_incidents or [],
            "processing": row.processing,
            "processing_error": row.processing_error,
        }
    )


def load_evidence_files(session: Session, claim_id: int) -> list[EvidenceFile]:
    rows = session.scalars(
        select(EvidenceFileRow)
        .where(EvidenceFileRow.claim_id == claim_id)
        .order_by(EvidenceFileRow.uploaded_at)
    ).all()
    return [evidence_file_to_schema(row) for row in rows]


def claim_to_schema(session: Optional[Session], row: ClaimRow) -> Claim:
    uploads: list[EvidenceFile] = []
    if session is not None:
        uploads = load_evidence_files(session, row.id)
    return Claim.model_validate(
        {
            "id": row.id,
            "reference": row.reference,
            "call_id": row.call_id,
            "status": row.status,
            "farmer": row.farmer or {},
            "crop": row.crop,
            "land_extent": row.land_extent,
            "damage_type": row.damage_type,
            "event_date": row.event_date,
            "event_date_confidence": row.event_date_confidence or 0.0,
            "location": row.location or {},
            "narrative": row.narrative or "",
            "weather_evidence": row.weather_evidence or {},
            "disaster_evidence": row.disaster_evidence or {},
            "crop_evidence": row.crop_evidence,
            "scheme_matches": row.scheme_matches or [],
            "unknowns": row.unknowns or [],
            "evidence_required": row.evidence_required or [],
            "evidence_uploads": [f.model_dump(mode="json") for f in uploads],
            "risk": row.risk or {},
            "escalation_reason": row.escalation_reason,
            "farmer_explanation": row.farmer_explanation,
            "reviewer_notes": row.reviewer_notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "agent_said_facts": row.agent_said_facts or [],
        }
    )


def ticket_to_schema(row: TicketRow) -> Ticket:
    return Ticket.model_validate(
        {
            "id": row.id,
            "claim_id": row.claim_id,
            "call_id": row.call_id,
            "reference": row.reference,
            "severity": row.severity,
            "reasons": row.reasons or [],
            "farmer_explanation": row.farmer_explanation or "",
            "status": row.status,
            "reviewer_notes": row.reviewer_notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def incidents_from_json(data: list | None) -> list[GuardrailIncident]:
    return coerce_list(GuardrailIncident, data or [])


def claim_summary(claim: Claim) -> dict:
    """Trimmed claim for list endpoints and WS payloads."""
    return {
        "id": claim.id,
        "reference": claim.reference,
        "call_id": claim.call_id,
        "status": claim.status,
        "farmer": claim.farmer.model_dump(mode="json"),
        "crop": claim.crop,
        "damage_type": claim.damage_type,
        "event_date": claim.event_date,
        "location": claim.location.model_dump(mode="json"),
        "verdict": claim.weather_evidence.verdict,
        "risk": claim.risk.model_dump(mode="json"),
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


__all__ = [
    "call_to_schema",
    "claim_to_schema",
    "claim_summary",
    "coerce",
    "evidence_file_to_schema",
    "evidence_file_url",
    "incidents_from_json",
    "load_evidence_files",
    "ticket_to_schema",
]
