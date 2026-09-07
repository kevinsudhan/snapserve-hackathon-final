"""Tickets: list and reviewer patch."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db import TicketRow, now_iso, read_session, session_scope
from app.events import emit
from app.schemas import Ticket, TicketPatch
from app.serializers import ticket_to_schema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tickets"])


@router.get("/tickets", response_model=list[Ticket])
async def list_tickets(
    status: str | None = Query(None), limit: int = Query(200, ge=1, le=1000)
) -> list[Ticket]:
    with read_session() as session:
        statement = select(TicketRow).order_by(TicketRow.id.desc())
        if status:
            statement = statement.where(TicketRow.status == status)
        rows = session.scalars(statement.limit(limit)).all()
        return [ticket_to_schema(row) for row in rows]


@router.get("/tickets/{ticket_id}", response_model=Ticket)
async def get_ticket(ticket_id: int) -> Ticket:
    with read_session() as session:
        row = session.get(TicketRow, ticket_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket_to_schema(row)


@router.patch("/tickets/{ticket_id}", response_model=Ticket)
async def patch_ticket(ticket_id: int, patch: TicketPatch) -> Ticket:
    with session_scope() as session:
        row = session.get(TicketRow, ticket_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if patch.status is not None:
            row.status = patch.status
        if patch.reviewer_notes is not None:
            row.reviewer_notes = patch.reviewer_notes
        row.updated_at = now_iso()
        session.flush()
        ticket = ticket_to_schema(row)

    await emit("ticket.updated", ticket.model_dump(mode="json"))
    logger.info("ticket %s -> %s", ticket.id, ticket.status)
    return ticket
