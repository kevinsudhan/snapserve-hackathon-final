"""Offline disaster cross-check against the GDACS events stored in the snapshot.

Like :mod:`services.weather`, this module never calls out. GDACS events were
pulled once by :mod:`services.knowledge_weather`; here we only filter them by
date overlap and distance.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from .knowledge_weather import GDACS_HOME, GDACS_TYPE_LABELS
from .models import Citation, DisasterEvent, DisasterEvidence
from .weather import haversine_km, load_snapshot

logger = logging.getLogger(__name__)

__all__ = ["check_disasters"]


def _parse(value: str) -> date | None:
    """Parse a leading ISO date, tolerating GDACS' datetime strings."""
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def check_disasters(
    lat: float,
    lon: float,
    event_date: str,
    *,
    radius_km: float = 300,
    days: int = 5,
    data_down: bool = False,
) -> DisasterEvidence:
    """Find GDACS events near a place and date, from the snapshot only.

    An event matches when its own from/to range, widened by ``days`` on both
    sides, contains ``event_date`` and its epicentre is within ``radius_km``.

    Args:
        lat: Latitude of the farm.
        lon: Longitude of the farm.
        event_date: ISO date the farmer reported.
        radius_km: Maximum distance from the event epicentre.
        days: Slack in days on either side of the event's own date range.
        data_down: Simulated outage; returns an empty ``source="none"`` result.

    Returns:
        A :class:`~services.models.DisasterEvidence`, events sorted nearest first.
    """
    if data_down:
        logger.info("data_down=True: skipping disaster cross-check")
        return DisasterEvidence(source="none")

    target = _parse(event_date)
    if target is None:
        logger.info("Unparseable event_date %r for disaster check", event_date)
        return DisasterEvidence(source="none")

    try:
        snapshot = load_snapshot()
    except FileNotFoundError as exc:
        logger.error("Snapshot missing for disaster check: %s", exc)
        return DisasterEvidence(source="none")

    matches: list[DisasterEvent] = []
    for event in snapshot.disasters:
        start, end = _parse(event.from_), _parse(event.to)
        if start is None or end is None:
            continue
        if not (start - timedelta(days=days) <= target <= end + timedelta(days=days)):
            continue
        if event.lat is None or event.lon is None:
            continue
        km = haversine_km(lat, lon, event.lat, event.lon)
        if km > radius_km:
            continue
        matches.append(event.model_copy(update={"distance_km": round(km, 1)}))

    matches.sort(key=lambda e: e.distance_km if e.distance_km is not None else 1e9)

    as_of = snapshot.generated_at[:10]
    citations = [
        Citation(
            id=f"D-{event.id}",
            title=(
                f"GDACS {GDACS_TYPE_LABELS.get(event.type, event.type)} "
                f"{event.alert_level}: {event.name} ({event.from_} to {event.to})"
            ),
            url=event.report_url,
            publisher="GDACS (JRC / UN OCHA)",
            as_of=as_of,
            kind="disaster",
        )
        for event in matches
    ]
    citations.append(
        Citation(
            id="D-gdacs",
            title="Global Disaster Alert and Coordination System",
            url=GDACS_HOME,
            publisher="GDACS (JRC / UN OCHA)",
            as_of=as_of,
            kind="disaster",
        )
    )

    logger.info(
        "Disaster check at (%s, %s) on %s: %s matching event(s)",
        lat,
        lon,
        event_date,
        len(matches),
    )
    return DisasterEvidence(
        source="gdacs",
        fetched_at=snapshot.generated_at,
        events=matches,
        citations=citations,
    )
