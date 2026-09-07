"""Offline weather truth-check.

Reads ``backend/data/weather_snapshot.json`` and nothing else. There is no
network call anywhere in this module: if the claim falls outside the snapshot's
coverage, or outside Tamil Nadu, or the snapshot is missing, the verdict is
``unverifiable`` -- never a guess.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from .knowledge_weather import (
    NOTABLE_GUST_KMH,
    NOTABLE_RAIN_MM,
    load_snapshot,
    slugify_district,
)
from .models import (
    Citation,
    SnapshotDistrict,
    WeatherDay,
    WeatherEvidence,
    WeatherSnapshot,
    WeatherWindow,
)

logger = logging.getLogger(__name__)

DAMAGE_TYPES = [
    "cyclone",
    "flood",
    "inundation",
    "heavy_rain",
    "unseasonal_rain",
    "drought",
    "hailstorm",
    "pest",
    "disease",
    "fire",
    "landslide",
    "other",
]

#: Damage types the daily rain/wind record cannot confirm or refute on its own.
WEATHER_NEUTRAL = {"hailstorm", "pest", "disease", "fire", "landslide", "other"}

#: +/- days of daily data examined around the event date, by damage type.
WINDOW_DAYS = {
    "cyclone": 3,
    "flood": 3,
    "inundation": 3,
    "heavy_rain": 2,
    "unseasonal_rain": 2,
}
DEFAULT_WINDOW_DAYS = 2
DROUGHT_LOOKBACK_DAYS = 45

#: A point further than this from every district centre is treated as outside
#: Tamil Nadu (the state's district centres are far denser than this).
MAX_DISTRICT_DISTANCE_KM = 150.0

CYCLONE_GUST_SUPPORTED = 60.0
CYCLONE_GUST_PARTIAL = 45.0
FLOOD_2DAY_SUPPORTED = 100.0
FLOOD_2DAY_PARTIAL = 50.0
FLOOD_DAY_PARTIAL = 35.0  # a single very wet day can leave water standing in a low field
RAIN_DAY_SUPPORTED = 50.0
RAIN_DAY_PARTIAL = 25.0
DROUGHT_SUPPORTED_RATIO = 0.30
DROUGHT_PARTIAL_RATIO = 0.60

CONTEXT_DAYS = 30
CHART_PAD_DAYS = 14
MAX_NEARBY_DATES = 5


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearest_district(
    lat: float, lon: float, snapshot: WeatherSnapshot | None = None
) -> tuple[SnapshotDistrict | None, float]:
    """Return the snapshot district nearest to a point, and the distance in km."""
    snap = snapshot or load_snapshot()
    best: SnapshotDistrict | None = None
    best_km = float("inf")
    for district in snap.districts:
        km = haversine_km(lat, lon, district.lat, district.lon)
        if km < best_km:
            best, best_km = district, km
    return best, best_km


# --------------------------------------------------------------------------- #
# snapshot access
# --------------------------------------------------------------------------- #
def fetch_daily(lat: float, lon: float, start: str, end: str) -> tuple[list[WeatherDay], str]:
    """Daily records for a point between two ISO dates, from the snapshot only.

    Args:
        lat: Latitude of the place.
        lon: Longitude of the place.
        start: Inclusive ISO start date.
        end: Inclusive ISO end date.

    Returns:
        ``(days, source_request_url)``. ``days`` is empty and the URL blank when
        no district is close enough or the snapshot has no overlap.
    """
    snapshot = load_snapshot()
    district, km = nearest_district(lat, lon, snapshot)
    if district is None or km > MAX_DISTRICT_DISTANCE_KM:
        logger.info("No Tamil Nadu district within %s km of (%s, %s)", MAX_DISTRICT_DISTANCE_KM, lat, lon)
        return [], ""
    days = [d for d in district.daily if start <= d.date <= end]
    return days, district.source_url


def weather_citation(cid: str) -> Citation | None:
    """Resolve ``W-<District>`` and ``W-<District>-<YYYY-MM-DD>`` citation ids.

    Day-level ids reuse the district's request URL (a single request covers the
    whole window) but carry the day's own numbers as the quote.
    """
    try:
        snapshot = load_snapshot()
    except FileNotFoundError:
        return None
    by_id = {c.id: c for c in snapshot.citations}
    if cid in by_id:
        return by_id[cid]

    parts = cid.rsplit("-", 3)
    if len(parts) == 4 and parts[0].startswith("W-"):
        base, iso = parts[0], "-".join(parts[1:])
        district_citation = by_id.get(base)
        if district_citation is None:
            return None
        slug = base[2:]
        for district in snapshot.districts:
            if slugify_district(district.name) != slug:
                continue
            for day in district.daily:
                if day.date != iso:
                    continue
                return district_citation.model_copy(
                    update={
                        "id": cid,
                        "title": f"Open-Meteo daily weather for {district.name} on {iso}",
                        "quote": (
                            f"{iso}: rain {day.precipitation_mm} mm, "
                            f"max gust {day.wind_gust_kmh} km/h, "
                            f"max temperature {day.temp_max_c} C"
                        ),
                    }
                )
    return None


def _citations_for(snapshot: WeatherSnapshot, district: SnapshotDistrict) -> list[Citation]:
    """The district request-URL citation plus the Open-Meteo docs citation."""
    wanted = {f"W-{slugify_district(district.name)}", "W-open-meteo-docs"}
    return [c for c in snapshot.citations if c.id in wanted]


# --------------------------------------------------------------------------- #
# verdict helpers
# --------------------------------------------------------------------------- #
def _best_2day(days: list[WeatherDay]) -> float:
    """Largest rain total over any two consecutive listed days."""
    if not days:
        return 0.0
    if len(days) == 1:
        return days[0].precipitation_mm
    return max(
        days[i].precipitation_mm + days[i + 1].precipitation_mm
        for i in range(len(days) - 1)
    )


def _window_for(damage_type: str, event: date) -> tuple[date, date]:
    """Inclusive date window examined for a damage type."""
    if damage_type == "drought":
        return event - timedelta(days=DROUGHT_LOOKBACK_DAYS - 1), event
    pad = WINDOW_DAYS.get(damage_type, DEFAULT_WINDOW_DAYS)
    return event - timedelta(days=pad), event + timedelta(days=pad)


def _unverifiable(
    window: WeatherWindow, reasons: list[str], sentence: str, metrics: dict | None = None
) -> WeatherEvidence:
    """Build an ``unverifiable`` result -- used for every "we do not know" path."""
    return WeatherEvidence(
        source="none",
        window=window,
        verdict="unverifiable",
        reasons=reasons,
        farmer_sentence=sentence,
        metrics=metrics or {},
    )


def _matching_dates(
    district: SnapshotDistrict, damage_type: str, event: date
) -> list[str]:
    """Dates anywhere in coverage that would meet the supported threshold.

    Sorted by how close they are to the reported date, so a farmer who
    misremembered by a few days can be gently offered the real one.
    """
    hits: list[str] = []
    daily = district.daily
    if damage_type == "cyclone":
        hits = [d.date for d in daily if d.wind_gust_kmh >= CYCLONE_GUST_SUPPORTED]
    elif damage_type in {"flood", "inundation"}:
        for i in range(len(daily) - 1):
            if daily[i].precipitation_mm + daily[i + 1].precipitation_mm >= FLOOD_2DAY_SUPPORTED:
                hits.append(daily[i + 1].date)
        hits += [d.date for d in daily if d.precipitation_mm >= FLOOD_DAY_PARTIAL and d.date not in hits]
    elif damage_type in {"heavy_rain", "unseasonal_rain"}:
        hits = [d.date for d in daily if d.precipitation_mm >= RAIN_DAY_SUPPORTED]
    elif damage_type in WEATHER_NEUTRAL:
        hits = [
            d.date
            for d in daily
            if d.precipitation_mm >= NOTABLE_RAIN_MM or d.wind_gust_kmh >= NOTABLE_GUST_KMH
        ]
    hits.sort(key=lambda iso: abs((date.fromisoformat(iso) - event).days))
    return hits[:MAX_NEARBY_DATES]


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def check_weather(
    lat: float,
    lon: float,
    event_date: str,
    damage_type: str,
    *,
    data_down: bool = False,
) -> WeatherEvidence:
    """Check whether the snapshot's weather record supports a reported damage.

    Args:
        lat: Latitude of the farm (usually a district centroid).
        lon: Longitude of the farm.
        event_date: ISO date the farmer reported.
        damage_type: One of :data:`DAMAGE_TYPES`.
        data_down: Simulated outage; forces ``unverifiable``.

    Returns:
        A :class:`~services.models.WeatherEvidence` with numbers, reasons, a
        plain-English sentence for the farmer, and the source citations.
    """
    damage_type = (damage_type or "other").strip().lower()
    if damage_type not in DAMAGE_TYPES:
        damage_type = "other"

    try:
        event = date.fromisoformat(event_date)
    except (TypeError, ValueError):
        blank = WeatherWindow(start="", end="")
        return _unverifiable(
            blank,
            [f"Could not read the event date {event_date!r} as a calendar date."],
            "I could not make out the exact date, so a person will check this with you.",
        )

    win_start, win_end = _window_for(damage_type, event)
    window = WeatherWindow(start=win_start.isoformat(), end=win_end.isoformat())

    if data_down:
        return _unverifiable(
            window,
            ["Weather data is switched off (data-down mode), so nothing was checked."],
            "I could not reach the weather record just now, so a person will verify this.",
        )

    try:
        snapshot = load_snapshot()
    except FileNotFoundError as exc:
        logger.error("Snapshot missing: %s", exc)
        return _unverifiable(
            window,
            ["The weather snapshot file has not been built yet."],
            "I could not reach the weather record just now, so a person will verify this.",
        )

    cov = snapshot.coverage
    if not cov.start or not cov.end:
        return _unverifiable(
            window,
            ["The weather snapshot is empty, so no date can be checked."],
            "I could not reach the weather record just now, so a person will verify this.",
        )

    district, km = nearest_district(lat, lon, snapshot)
    if district is None or km > MAX_DISTRICT_DISTANCE_KM:
        return _unverifiable(
            window,
            [
                f"The place given is {km:.0f} km from the nearest Tamil Nadu district "
                f"centre, so it is outside the area this record covers "
                f"({cov.start} to {cov.end})."
            ],
            "That place is outside the area I have weather records for, so a person will check it.",
            {"distance_km": round(km, 1)},
        )

    if not (cov.start <= event_date <= cov.end):
        return _unverifiable(
            window,
            [
                f"{event_date} is outside the weather record, which covers "
                f"{cov.start} to {cov.end} only."
            ],
            (
                f"My weather record only covers {cov.start} to {cov.end}, so I cannot "
                "check that date myself - a person will look into it."
            ),
            {"distance_km": round(km, 1), "district_used": district.name},
        )

    by_date = {d.date: d for d in district.daily}
    win_days = [
        d
        for d in district.daily
        if win_start.isoformat() <= d.date <= win_end.isoformat()
    ]
    ctx_start = (event - timedelta(days=CONTEXT_DAYS - 1)).isoformat()
    ctx_days = [d for d in district.daily if ctx_start <= d.date <= event_date]
    context_30d = round(sum(d.precipitation_mm for d in ctx_days), 1)

    max_gust = max((d.wind_gust_kmh for d in win_days), default=0.0)
    max_rain = max((d.precipitation_mm for d in win_days), default=0.0)
    window_rain = round(sum(d.precipitation_mm for d in win_days), 1)
    best_2day = round(_best_2day(win_days), 1)

    metrics: dict[str, float | str] = {
        "max_gust_kmh": round(max_gust, 1),
        "max_daily_rain_mm": round(max_rain, 1),
        "window_rain_mm": window_rain,
        "best_2day_rain_mm": best_2day,
        "context_30d_rain_mm": context_30d,
        "district_used": district.name,
        "distance_km": round(km, 1),
    }

    on_day = by_date.get(event_date)
    reasons: list[str] = [
        f"Checked the Open-Meteo record for {district.name} "
        f"({km:.0f} km from the place given), {window.start} to {window.end}."
    ]
    if on_day is not None:
        reasons.append(
            f"On {event_date} itself: {on_day.precipitation_mm:.1f} mm of rain, "
            f"gusts up to {on_day.wind_gust_kmh:.0f} km/h, "
            f"highest temperature {on_day.temp_max_c:.0f} C."
        )

    verdict, extra_reasons, sentence = _judge(
        damage_type=damage_type,
        district=district,
        event=event,
        event_date=event_date,
        win_days=win_days,
        max_gust=max_gust,
        max_rain=max_rain,
        window_rain=window_rain,
        best_2day=best_2day,
        metrics=metrics,
        snapshot=snapshot,
    )
    reasons.extend(extra_reasons)

    chart_start = (event - timedelta(days=CHART_PAD_DAYS)).isoformat()
    chart_end = (event + timedelta(days=CHART_PAD_DAYS)).isoformat()
    chart = [d for d in district.daily if chart_start <= d.date <= chart_end]

    return WeatherEvidence(
        source="snapshot",
        request_url=district.source_url,
        fetched_at=snapshot.generated_at,
        window=window,
        daily=chart,
        context_30d_rain_mm=context_30d,
        metrics=metrics,
        verdict=verdict,
        reasons=reasons,
        farmer_sentence=sentence,
        nearby_matching_dates=_matching_dates(district, damage_type, event),
        citations=_citations_for(snapshot, district),
    )


def _judge(
    *,
    damage_type: str,
    district: SnapshotDistrict,
    event: date,
    event_date: str,
    win_days: list[WeatherDay],
    max_gust: float,
    max_rain: float,
    window_rain: float,
    best_2day: float,
    metrics: dict[str, float | str],
    snapshot: WeatherSnapshot,
) -> tuple[str, list[str], str]:
    """Apply the per-damage-type thresholds. Returns (verdict, reasons, sentence)."""
    reasons: list[str] = []

    if damage_type == "cyclone":
        reasons.append(
            f"Strongest gust in the window was {max_gust:.0f} km/h "
            f"(cyclone damage is supported from {CYCLONE_GUST_SUPPORTED:.0f} km/h)."
        )
        if max_gust >= CYCLONE_GUST_SUPPORTED:
            return (
                "supported",
                reasons,
                f"The weather record for {district.name} around {event_date} does show "
                f"very strong wind, up to {max_gust:.0f} km per hour. That matches what you described.",
            )
        if max_gust >= CYCLONE_GUST_PARTIAL:
            return (
                "partially_supported",
                reasons,
                f"The record shows strong wind near {event_date}, about {max_gust:.0f} km per hour. "
                "That is high but not full cyclone strength, so a person will look at it with you.",
            )
        return (
            "not_supported",
            reasons,
            f"The weather record for {district.name} around {event_date} shows wind of only about "
            f"{max_gust:.0f} km per hour, which does not match a cyclone. Could the date or the place be different?",
        )

    if damage_type in {"flood", "inundation"}:
        reasons.append(
            f"Heaviest two days together brought {best_2day:.1f} mm of rain "
            f"(flooding is supported from {FLOOD_2DAY_SUPPORTED:.0f} mm over two days)."
        )
        if best_2day >= FLOOD_2DAY_SUPPORTED:
            return (
                "supported",
                reasons,
                f"Yes, the record shows very heavy rain near {event_date} - about {best_2day:.0f} mm "
                "over two days around your area. That fits water standing in the field.",
            )
        if best_2day >= FLOOD_2DAY_PARTIAL or max_rain >= FLOOD_DAY_PARTIAL:
            reasons.append(
                f"Wettest single day brought {max_rain:.1f} mm "
                f"(standing water is partially supported from {FLOOD_DAY_PARTIAL:.0f} mm in a day)."
            )
            return (
                "partially_supported",
                reasons,
                f"The record shows heavy rain near {event_date}, about {max(best_2day, max_rain):.0f} mm. "
                "It may be enough in a low-lying field, so a person will check it with you.",
            )
        return (
            "not_supported",
            reasons,
            f"The rain record for {district.name} around {event_date} shows only about "
            f"{best_2day:.0f} mm over two days, which is usually not enough to flood a field. "
            "Could the date be a different one?",
        )

    if damage_type in {"heavy_rain", "unseasonal_rain"}:
        reasons.append(
            f"Wettest single day in the window was {max_rain:.1f} mm "
            f"(heavy rain is supported from {RAIN_DAY_SUPPORTED:.0f} mm in a day)."
        )
        if max_rain >= RAIN_DAY_SUPPORTED:
            return (
                "supported",
                reasons,
                f"Yes - the record shows about {max_rain:.0f} mm of rain in one day near {event_date}. "
                "That is heavy rain.",
            )
        if max_rain >= RAIN_DAY_PARTIAL:
            return (
                "partially_supported",
                reasons,
                f"There was moderate rain near {event_date}, about {max_rain:.0f} mm in a day. "
                "A person will look at whether that was enough to damage your crop.",
            )
        return (
            "not_supported",
            reasons,
            f"The rain record for {district.name} around {event_date} shows only about "
            f"{max_rain:.0f} mm in a day, which is not heavy rain. Could the date be different?",
        )

    if damage_type == "drought":
        all_days = district.daily
        daily_avg = (
            sum(d.precipitation_mm for d in all_days) / len(all_days) if all_days else 0.0
        )
        baseline = daily_avg * DROUGHT_LOOKBACK_DAYS
        metrics["baseline_45d_rain_mm"] = round(baseline, 1)
        metrics["baseline_daily_avg_mm"] = round(daily_avg, 2)
        reasons.append(
            f"Rain in the {DROUGHT_LOOKBACK_DAYS} days up to {event_date} was "
            f"{window_rain:.1f} mm."
        )
        reasons.append(
            "Baseline used: this district's own average over the whole "
            f"{len(all_days)}-day snapshot ({daily_avg:.2f} mm a day, so "
            f"{baseline:.0f} mm over {DROUGHT_LOOKBACK_DAYS} days). This is a short-period "
            "comparison, not a long-term normal, so treat it as a first indication only."
        )
        if baseline <= 0:
            return (
                "unverifiable",
                reasons + ["The snapshot has no rain at all for this district, so no baseline exists."],
                "I do not have enough rain history for your area to judge dryness, so a person will check it.",
            )
        ratio = window_rain / baseline
        metrics["drought_ratio"] = round(ratio, 3)
        reasons.append(f"That is {ratio * 100:.0f} % of the baseline.")
        if ratio < DROUGHT_SUPPORTED_RATIO:
            return (
                "supported",
                reasons,
                f"The record does show a dry spell - about {window_rain:.0f} mm of rain in the "
                f"{DROUGHT_LOOKBACK_DAYS} days before {event_date}, well below the usual level for your area "
                "in this snapshot.",
            )
        if ratio < DROUGHT_PARTIAL_RATIO:
            return (
                "partially_supported",
                reasons,
                f"Rain was on the low side before {event_date} - about {window_rain:.0f} mm in "
                f"{DROUGHT_LOOKBACK_DAYS} days. It is drier than usual but not severely, so a person will check it.",
            )
        return (
            "not_supported",
            reasons,
            f"The record shows about {window_rain:.0f} mm of rain in the {DROUGHT_LOOKBACK_DAYS} days before "
            f"{event_date} for {district.name}, which does not look like a drought. "
            "A person can still look at your field.",
        )

    # Weather-neutral damage types: hail, pest, disease, fire, landslide, other.
    notable = [
        d
        for d in win_days
        if d.precipitation_mm >= NOTABLE_RAIN_MM or d.wind_gust_kmh >= NOTABLE_GUST_KMH
    ]
    reasons.append(
        f"Daily rain and wind records cannot confirm or rule out {damage_type.replace('_', ' ')} "
        "damage; that needs field evidence such as photographs and a field visit."
    )
    if notable:
        days_text = ", ".join(
            f"{d.date} ({d.precipitation_mm:.1f} mm, gust {d.wind_gust_kmh:.0f} km/h)"
            for d in notable
        )
        reasons.append(f"There was disturbed weather nearby: {days_text}.")
        return (
            "partially_supported",
            reasons,
            "The weather around that date was rough, but rain and wind figures alone cannot show "
            "this kind of damage. Photographs of the field will help, and a person will check.",
        )
    reasons.append("The window was calm: no day reached 10 mm of rain or a 45 km/h gust.")
    return (
        "unverifiable",
        reasons,
        "Weather records cannot show this kind of damage, so I cannot confirm it myself. "
        "Photographs of the field will help, and a person will check it with you.",
    )
