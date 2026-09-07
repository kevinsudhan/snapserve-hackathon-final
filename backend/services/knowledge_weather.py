"""One-off weather + disaster snapshot builder.

This is the **only** module in the project that touches the network. It pulls the
past ``days`` days (through yesterday) of daily weather for every Tamil Nadu
district from the Open-Meteo Forecast API, plus GDACS TC/FL/DR events for India
in the same window, and writes them to ``backend/data/weather_snapshot.json``.

Everything downstream -- the agent prompt, ``services.weather``,
``services.disasters`` and the dashboard map -- reads that file and never calls
out. Re-running the CLI is the only way new data enters the system::

    cd backend && python -m services.knowledge_weather --days 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx

from .models import (
    Citation,
    DisasterEvent,
    SnapshotDistrict,
    WeatherDay,
    WeatherSnapshot,
    WeatherWindow,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DISTRICTS_PATH = DATA_DIR / "tn_districts.json"
SNAPSHOT_PATH = DATA_DIR / "weather_snapshot.json"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_DAILY = (
    "precipitation_sum,precipitation_hours,wind_gusts_10m_max,"
    "wind_speed_10m_max,temperature_2m_max"
)
OPEN_METEO_DOCS = "https://open-meteo.com/en/docs"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GDACS_HOME = "https://www.gdacs.org"

#: A day is "notable" (and therefore spelled out in the prompt) above these.
NOTABLE_RAIN_MM = 10.0
NOTABLE_GUST_KMH = 45.0

MAX_CONCURRENCY = 6
TIMEOUT_SECONDS = 10.0
RETRIES = 2
#: GDACS is a single request and noticeably flakier than Open-Meteo, so it gets
#: a longer timeout and more attempts.
GDACS_TIMEOUT_SECONDS = 30.0
GDACS_RETRIES = 4
USER_AGENT = "Araxys Desk/1.0 (crop-insurance claims desk; one-off snapshot)"

# GDACS event type code -> readable label.
GDACS_TYPE_LABELS = {"TC": "Tropical cyclone", "FL": "Flood", "DR": "Drought"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def slugify_district(name: str) -> str:
    """``"The Nilgiris"`` -> ``"TheNilgiris"`` for use inside citation ids."""
    return "".join(part for part in name.replace("-", " ").split() if part)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4) used to keep the prompt inside budget."""
    return len(text) // 4


def load_districts() -> list[dict]:
    """Read the offline district centroid table."""
    with DISTRICTS_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["districts"]


def _f(value: float | int | None) -> float:
    """Open-Meteo sends ``null`` for missing values; treat those as zero."""
    return float(value) if value is not None else 0.0


def _district_url(lat: float, lon: float, days: int) -> str:
    """Build the exact Open-Meteo request URL that is stored as the citation."""
    return (
        f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
        f"&past_days={days}&forecast_days=1&daily={OPEN_METEO_DAILY}"
        "&timezone=Asia/Kolkata"
    )


# --------------------------------------------------------------------------- #
# network
# --------------------------------------------------------------------------- #
async def _fetch_district(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    district: dict,
    days: int,
    cutoff: date,
) -> SnapshotDistrict:
    """Fetch one district's daily series, dropping any day after ``cutoff``."""
    url = _district_url(district["lat"], district["lon"], days)
    last_error: Exception | None = None
    async with sem:
        for attempt in range(RETRIES + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised
                last_error = exc
                logger.warning(
                    "Open-Meteo attempt %s/%s failed for %s: %s",
                    attempt + 1,
                    RETRIES + 1,
                    district["name"],
                    exc,
                )
                if attempt < RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
        else:  # pragma: no cover - loop always breaks or exhausts
            raise RuntimeError(f"Open-Meteo failed for {district['name']}") from last_error

    daily_raw = payload["daily"]
    days_out: list[WeatherDay] = []
    notable: list[str] = []
    for i, iso in enumerate(daily_raw["time"]):
        if date.fromisoformat(iso) > cutoff:
            continue  # slice off the forecast day
        day = WeatherDay(
            date=iso,
            precipitation_mm=round(_f(daily_raw["precipitation_sum"][i]), 1),
            wind_gust_kmh=round(_f(daily_raw["wind_gusts_10m_max"][i]), 1),
            temp_max_c=round(_f(daily_raw["temperature_2m_max"][i]), 1),
            precipitation_hours=round(_f(daily_raw["precipitation_hours"][i]), 1),
            wind_speed_kmh=round(_f(daily_raw["wind_speed_10m_max"][i]), 1),
        )
        days_out.append(day)
        if day.precipitation_mm >= NOTABLE_RAIN_MM or day.wind_gust_kmh >= NOTABLE_GUST_KMH:
            notable.append(day.date)

    logger.info(
        "%s: %s days, %s notable", district["name"], len(days_out), len(notable)
    )
    return SnapshotDistrict(
        name=district["name"],
        lat=district["lat"],
        lon=district["lon"],
        source_url=url,
        daily=days_out,
        notable=notable,
    )


async def _fetch_disasters(
    client: httpx.AsyncClient, start: date, end: date
) -> tuple[list[DisasterEvent], str]:
    """Fetch GDACS TC/FL/DR events for India overlapping the coverage window."""
    url = (
        f"{GDACS_URL}?eventlist=TC,FL,DR&country=India"
        f"&fromDate={start.isoformat()}&toDate={end.isoformat()}"
    )
    last_error: Exception | None = None
    payload: dict | None = None
    for attempt in range(GDACS_RETRIES + 1):
        try:
            response = await client.get(url, timeout=GDACS_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            break
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            last_error = exc
            logger.warning(
                "GDACS attempt %s/%s failed: %r", attempt + 1, GDACS_RETRIES + 1, exc
            )
            if attempt < GDACS_RETRIES:
                await asyncio.sleep(2.0 * (attempt + 1))
    if payload is None:
        raise RuntimeError("GDACS event list unreachable") from last_error

    events: list[DisasterEvent] = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry") or {}
        lat = lon = None
        if geom.get("type") == "Point":
            coords = geom.get("coordinates") or []
            if len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
        event_id = str(props.get("eventid"))
        report = (props.get("url") or {}).get("report") or (
            f"{GDACS_HOME}/report.aspx?eventid={event_id}"
        )
        events.append(
            DisasterEvent(
                id=event_id,
                type=str(props.get("eventtype") or "").upper(),
                name=str(props.get("name") or props.get("description") or "Event"),
                alert_level=str(props.get("alertlevel") or "Unknown"),
                **{"from": str(props.get("fromdate") or "")[:10]},
                to=str(props.get("todate") or "")[:10],
                report_url=report,
                lat=lat,
                lon=lon,
            )
        )
    logger.info("GDACS: %s events for India in window", len(events))
    return events, url


async def _build_async(days: int) -> WeatherSnapshot:
    """Async core of :func:`build_weather_snapshot`."""
    districts = load_districts()
    now = datetime.now(timezone.utc)
    cutoff = date.today() - timedelta(days=1)  # coverage ends yesterday
    start = cutoff - timedelta(days=days - 1)
    as_of = now.date().isoformat()

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    limits = httpx.Limits(max_connections=MAX_CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, headers={"user-agent": USER_AGENT}, limits=limits
    ) as client:
        district_results = await asyncio.gather(
            *(_fetch_district(client, sem, d, days, cutoff) for d in districts)
        )
        try:
            events, gdacs_url = await _fetch_disasters(client, start, cutoff)
        except Exception as exc:  # noqa: BLE001 - disasters are best effort
            logger.error("GDACS fetch failed, continuing without events: %s", exc)
            events, gdacs_url = [], ""

    # Real coverage is whatever every district actually returned.
    covered = [d.daily[0].date for d in district_results if d.daily]
    covered_end = [d.daily[-1].date for d in district_results if d.daily]
    coverage = WeatherWindow(
        start=max(covered) if covered else start.isoformat(),
        end=min(covered_end) if covered_end else cutoff.isoformat(),
    )

    citations: list[Citation] = [
        Citation(
            id=f"W-{slugify_district(d.name)}",
            title=(
                f"Open-Meteo daily weather for {d.name}, Tamil Nadu "
                f"({coverage.start} to {coverage.end})"
            ),
            url=d.source_url,
            publisher="Open-Meteo",
            as_of=as_of,
            kind="weather",
        )
        for d in district_results
    ]
    citations.append(
        Citation(
            id="W-open-meteo-docs",
            title="Open-Meteo Weather Forecast API documentation",
            url=OPEN_METEO_DOCS,
            publisher="Open-Meteo",
            as_of=as_of,
            kind="weather",
        )
    )
    for event in events:
        citations.append(
            Citation(
                id=f"D-{event.id}",
                title=f"GDACS {GDACS_TYPE_LABELS.get(event.type, event.type)}: {event.name}",
                url=event.report_url,
                publisher="GDACS (JRC / UN OCHA)",
                as_of=as_of,
                kind="disaster",
            )
        )
    if gdacs_url:
        citations.append(
            Citation(
                id="D-gdacs",
                title="GDACS event list for India (TC/FL/DR) over the coverage window",
                url=gdacs_url,
                publisher="GDACS (JRC / UN OCHA)",
                as_of=as_of,
                kind="disaster",
            )
        )

    return WeatherSnapshot(
        generated_at=now.isoformat(timespec="seconds"),
        days=days,
        coverage=coverage,
        districts=list(district_results),
        disasters=events,
        citations=citations,
    )


def build_weather_snapshot(days: int = 60, *, data_down: bool = False) -> WeatherSnapshot:
    """Pull real weather + disaster data once and write the snapshot file.

    Args:
        days: How many past days to request (coverage ends yesterday).
        data_down: Simulated outage. Skips the network entirely and returns an
            empty snapshot, so every downstream check reports ``unverifiable``
            rather than inventing numbers.

    Returns:
        The snapshot that was written to ``backend/data/weather_snapshot.json``.
    """
    if data_down:
        logger.warning("data_down=True: skipping network, writing an empty snapshot")
        now = datetime.now(timezone.utc)
        empty = WeatherSnapshot(
            generated_at=now.isoformat(timespec="seconds"),
            days=days,
            coverage=WeatherWindow(start="", end=""),
        )
        _write(empty)
        return empty

    snapshot = asyncio.run(_build_async(days))
    _write(snapshot)
    logger.info(
        "Snapshot written: %s districts, %s..%s, %s disaster events",
        len(snapshot.districts),
        snapshot.coverage.start,
        snapshot.coverage.end,
        len(snapshot.disasters),
    )
    return snapshot


def _write(snapshot: WeatherSnapshot) -> None:
    """Persist the snapshot and drop the in-process cache."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot.model_dump(by_alias=True), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    load_snapshot.cache_clear()


# --------------------------------------------------------------------------- #
# offline readers
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_snapshot() -> WeatherSnapshot:
    """Cached read of ``backend/data/weather_snapshot.json``.

    Raises:
        FileNotFoundError: if the snapshot has never been built.
    """
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"{SNAPSHOT_PATH} not found - run "
            "`python -m services.knowledge_weather --days 60` from backend/"
        )
    with SNAPSHOT_PATH.open(encoding="utf-8") as fh:
        return WeatherSnapshot.model_validate(json.load(fh))


# --------------------------------------------------------------------------- #
# prompt rendering
# --------------------------------------------------------------------------- #
def _pretty(iso: str) -> str:
    """``2026-07-08`` -> ``Jul 08``."""
    return date.fromisoformat(iso).strftime("%b %d")


def _weekly_lines(district: SnapshotDistrict) -> list[str]:
    """Seven-day rain totals and peak gusts across the coverage window."""
    lines: list[str] = []
    for i in range(0, len(district.daily), 7):
        chunk = district.daily[i : i + 7]
        if not chunk:
            continue
        rain = sum(d.precipitation_mm for d in chunk)
        gust = max(d.wind_gust_kmh for d in chunk)
        lines.append(
            f"{_pretty(chunk[0].date)}-{_pretty(chunk[-1].date)}: "
            f"{rain:.0f} mm, max gust {gust:.0f} km/h"
        )
    return lines


def _nearest_districts(
    snapshot: WeatherSnapshot, lat: float | None, lon: float | None, radius_km: float
) -> list[str]:
    """District names within ``radius_km`` of a point, nearest first."""
    if lat is None or lon is None:
        return []
    from .weather import haversine_km  # local import: avoids a circular import

    near = sorted(
        (
            (haversine_km(lat, lon, d.lat, d.lon), d.name)
            for d in snapshot.districts
        )
    )
    return [name for dist, name in near if dist <= radius_km]


def render_weather_knowledge(snapshot: WeatherSnapshot) -> str:
    """Render the snapshot as compact prompt text with quotable citation ids.

    The first block is a rule block that tells the agent exactly what the absence
    of a line means, so it never reads silence as "no weather data".
    """
    out: list[str] = []
    cov = snapshot.coverage
    out.append(
        f"Coverage: {cov.start} to {cov.end}, Tamil Nadu districts only, "
        f"source Open-Meteo (generated {snapshot.generated_at}). "
        "If a date inside the coverage is not listed for a district, that day had "
        "under 10 mm rain and gusts under 45 km/h. "
        "Dates outside coverage or places outside Tamil Nadu: you do NOT know - "
        "say you cannot verify and a reviewer will check."
    )
    out.append(
        "Day lines read: [id] <rain>mm <max gust>kmh <max temperature>C. "
        "Quote the id in square brackets whenever you state one of these numbers."
    )
    out.append("")

    for district in snapshot.districts:
        if not district.daily:
            continue
        slug = slugify_district(district.name)
        total = sum(d.precipitation_mm for d in district.daily)
        last7 = sum(d.precipitation_mm for d in district.daily[-7:])
        peak = max(district.daily, key=lambda d: d.wind_gust_kmh)
        out.append(
            f"[W-{slug}] {district.name}: {len(district.daily)}-day rain "
            f"{total:.0f} mm, last 7 days {last7:.0f} mm, "
            f"max gust {peak.wind_gust_kmh:.0f} km/h on {peak.date}."
        )
        for line in _weekly_lines(district):
            out.append(f"  {line}")
        by_date = {d.date: d for d in district.daily}
        for iso in district.notable:
            day = by_date.get(iso)
            if day is None:
                continue
            out.append(
                f"  [W-{slug}-{day.date}] {day.precipitation_mm:.1f}mm "
                f"{day.wind_gust_kmh:.0f}kmh {day.temp_max_c:.0f}C"
            )
        out.append("")

    if snapshot.disasters:
        out.append("Disaster alerts (GDACS, India, same window):")
        for event in snapshot.disasters:
            near = _nearest_districts(snapshot, event.lat, event.lon, 300.0)
            where = ", ".join(near[:6]) if near else "no Tamil Nadu district within 300 km"
            label = GDACS_TYPE_LABELS.get(event.type, event.type)
            out.append(
                f"[D-{event.id}] {label} {event.alert_level} {event.name} "
                f"{event.from_} to {event.to} ({where})"
            )
        out.append("")
    else:
        out.append(
            "Disaster alerts (GDACS, India, same window): none recorded. "
            "Absence of a GDACS alert does not by itself disprove a farmer's report."
        )

    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m services.knowledge_weather --days 60``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=60, help="past days to pull")
    parser.add_argument(
        "--data-down", action="store_true", help="simulate an outage (no network)"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    snapshot = build_weather_snapshot(args.days, data_down=args.data_down)
    text = render_weather_knowledge(snapshot)
    logger.info(
        "Rendered weather knowledge: %s chars, ~%s tokens",
        len(text),
        estimate_tokens(text),
    )
    logger.info("Wrote %s (%.1f KB)", SNAPSHOT_PATH, SNAPSHOT_PATH.stat().st_size / 1024)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
