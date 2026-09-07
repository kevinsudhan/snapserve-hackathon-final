"""GET /api/stats"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db import CallRow, ClaimRow, GuardrailIncidentRow, TicketRow, read_session
from app.schemas import HourBucket, StatsResponse

router = APIRouter(prefix="/api", tags=["stats"])

_VERDICTS = ("supported", "partially_supported", "not_supported", "unverifiable")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    with read_session() as session:
        calls_total = session.scalar(select(func.count()).select_from(CallRow)) or 0
        claims_total = session.scalar(select(func.count()).select_from(ClaimRow)) or 0
        tickets_open = (
            session.scalar(
                select(func.count()).select_from(TicketRow).where(TicketRow.status == "open")
            )
            or 0
        )
        incidents = session.scalar(select(func.count()).select_from(GuardrailIncidentRow)) or 0

        languages: dict[str, int] = {}
        for (language,) in session.execute(
            select(CallRow.language_detected).where(CallRow.language_detected.is_not(None))
        ):
            if language:
                languages[language] = languages.get(language, 0) + 1

        verdicts = {verdict: 0 for verdict in _VERDICTS}
        for (evidence,) in session.execute(select(ClaimRow.weather_evidence)):
            verdict = (evidence or {}).get("verdict")
            if verdict in verdicts:
                verdicts[verdict] += 1

        started = [row for (row,) in session.execute(select(CallRow.started_at))]

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    window = [now - timedelta(hours=offset) for offset in range(23, -1, -1)]
    buckets = {hour.isoformat(): 0 for hour in window}
    cutoff = window[0]
    for value in started:
        parsed = _parse(value)
        if parsed is None:
            continue
        hour = parsed.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if hour >= cutoff:
            key = hour.isoformat()
            if key in buckets:
                buckets[key] += 1

    return StatsResponse(
        calls_total=calls_total,
        claims_total=claims_total,
        tickets_open=tickets_open,
        guardrail_incidents=incidents,
        languages=languages,
        verdicts=verdicts,
        last_24h=[HourBucket(hour=hour, calls=count) for hour, count in buckets.items()],
    )
