"""Shared pydantic v2 models for Araxys Desk data services.

Field names here are binding: they mirror the TypeScript shapes in
``docs/CONTRACTS.md`` exactly, because the core worker imports these models and
the dashboard mirrors them in ``dashboard/src/types.ts``.

Nothing in this module touches the network.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CitationKind = Literal["scheme", "weather", "disaster", "crop", "gazetteer", "other"]
Verdict = Literal["supported", "partially_supported", "not_supported", "unverifiable"]

__all__ = [
    "Citation",
    "Location",
    "LandExtent",
    "WeatherDay",
    "WeatherWindow",
    "WeatherEvidence",
    "DisasterEvent",
    "DisasterEvidence",
    "CropEvidence",
    "CropWindow",
    "SnapshotDistrict",
    "WeatherSnapshot",
    "CitationKind",
    "Verdict",
]


class Citation(BaseModel):
    """A resolvable source reference. ``id`` is what the agent may speak."""

    id: str
    title: str
    url: str
    publisher: str
    page: int | str | None = None
    as_of: str
    quote: str | None = None
    kind: CitationKind = "other"


class Location(BaseModel):
    """A resolved place. ``lat``/``lon`` are the district centroid when known."""

    village: str | None = None
    taluk: str | None = None
    district: str | None = None
    state: str = "Tamil Nadu"
    lat: float | None = None
    lon: float | None = None
    resolution_confidence: float = 0.0
    resolved_by: str | None = None
    citation_id: str | None = None


class LandExtent(BaseModel):
    """A land area normalised to hectares."""

    value: float
    unit: str
    hectares: float


class WeatherDay(BaseModel):
    """One daily record from the snapshot.

    ``precipitation_hours`` and ``wind_speed_kmh`` are snapshot extras beyond the
    contract's minimum three fields; consumers may ignore them.
    """

    date: str
    precipitation_mm: float
    wind_gust_kmh: float
    temp_max_c: float
    precipitation_hours: float | None = None
    wind_speed_kmh: float | None = None


class WeatherWindow(BaseModel):
    """The inclusive date window a verdict was computed over."""

    start: str
    end: str


class WeatherEvidence(BaseModel):
    """Result of the offline weather truth-check for one claim."""

    source: Literal["snapshot", "none"] = "none"
    request_url: str | None = None
    fetched_at: str | None = None
    window: WeatherWindow
    daily: list[WeatherDay] = Field(default_factory=list)
    context_30d_rain_mm: float | None = None
    #: Mostly numeric, but ``district_used`` is a district name, so the value
    #: type is widened to ``float | str``.
    metrics: dict[str, float | str] = Field(default_factory=dict)
    verdict: Verdict = "unverifiable"
    reasons: list[str] = Field(default_factory=list)
    farmer_sentence: str = ""
    nearby_matching_dates: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class DisasterEvent(BaseModel):
    """A GDACS event. ``from_``/``to`` serialise as ``from``/``to`` per contract."""

    id: str
    type: str
    name: str
    alert_level: str
    from_: str = Field(alias="from")
    to: str
    distance_km: float | None = None
    report_url: str
    lat: float | None = None
    lon: float | None = None

    model_config = {"populate_by_name": True}


class DisasterEvidence(BaseModel):
    """Nearby GDACS events for a claim, read from the snapshot only."""

    source: Literal["gdacs", "none"] = "none"
    fetched_at: str | None = None
    events: list[DisasterEvent] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class CropWindow(BaseModel):
    """Human-readable sowing / harvest window text for one calendar entry."""

    sowing: str
    harvest: str


class CropEvidence(BaseModel):
    """Whether an event date falls inside a crop's growing window."""

    crop: str
    district: str | None = None
    season: str | None = None
    in_window: bool | None = None
    window: CropWindow | None = None
    note: str = ""
    citations: list[Citation] = Field(default_factory=list)


class SnapshotDistrict(BaseModel):
    """One district's 60-day daily series inside the snapshot."""

    name: str
    lat: float
    lon: float
    source_url: str
    daily: list[WeatherDay] = Field(default_factory=list)
    notable: list[str] = Field(default_factory=list)


class WeatherSnapshot(BaseModel):
    """The one-off, on-disk weather + disaster snapshot everything else reads."""

    generated_at: str
    days: int
    coverage: WeatherWindow
    districts: list[SnapshotDistrict] = Field(default_factory=list)
    disasters: list[DisasterEvent] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
