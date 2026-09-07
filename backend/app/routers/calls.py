"""GET /api/calls, GET /api/calls/{id}"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db import CallRow, read_session
from app.schemas import CallRecord
from app.serializers import call_to_schema

router = APIRouter(prefix="/api", tags=["calls"])


@router.get("/calls", response_model=list[CallRecord])
async def list_calls(limit: int = Query(50, ge=1, le=500)) -> list[CallRecord]:
    """Newest first."""
    with read_session() as session:
        rows = session.scalars(
            select(CallRow).order_by(CallRow.id.desc()).limit(limit)
        ).all()
        return [call_to_schema(row) for row in rows]


@router.get("/calls/{call_id}", response_model=CallRecord)
async def get_call(call_id: int) -> CallRecord:
    with read_session() as session:
        row = session.get(CallRow, call_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Call not found")
        return call_to_schema(row)
