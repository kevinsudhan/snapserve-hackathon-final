"""Pydantic models — the single source of truth for the API payload shapes.

These mirror ``docs/CONTRACTS.md`` field-for-field.  The data/schemes workers
build their own models in ``services/models.py`` / ``services/schemes_models.py``
following the same contract; :func:`coerce` converts whatever object they hand
back (pydantic model, dataclass, dict) into the models below, so a small
divergence in their internals never breaks the API surface.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# literals
# --------------------------------------------------------------------------
CitationKind = Literal["scheme", "weather", "disaster", "crop", "gazetteer", "other"]
TurnRole = Literal["agent", "caller"]
CallDirection = Literal["inbound", "outbound", "webcall", "simulated"]
CallStatus = Literal["in_progress", "completed", "failed", "no_pickup"]
ProcessingState = Literal["pending", "processing", "done", "error"]
Verdict = Literal["supported", "partially_supported", "not_supported", "unverifiable"]
RiskLevel = Literal["low", "medium", "high"]
Severity = Literal["low", "medium", "high"]
ClaimStatus = Literal["logged", "escalated", "under_review", "approved_for_survey", "closed"]
TicketStatus = Literal["open", "in_review", "resolved", "rejected"]
QualityFlag = Literal["ok", "blurry", "not_relevant", "unchecked"]
GuardrailCategory = Literal[
    "payout_promise",
    "approval_promise",
    "timeline_promise",
    "fabricated_scheme",
    "out_of_scope_advice",
    "missed_escalation",
    "other",
]
DetectorKind = Literal["rules", "llm"]


class Base(BaseModel):
    """Lenient base: unknown keys from sibling workers are dropped, not fatal."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# --------------------------------------------------------------------------
# citations & transcript
# --------------------------------------------------------------------------
class Citation(Base):
    id: str
    title: str
    url: str
    publisher: str = ""
    page: Optional[str | int] = None
    as_of: str = ""
    quote: Optional[str] = None
    kind: CitationKind = "other"


class TranscriptTurn(Base):
    i: int
    role: TurnRole
    text: str
    language: Optional[str] = None
    flags: list[str] = Field(default_factory=list)


class GuardrailIncident(Base):
    turn_index: int
    category: GuardrailCategory
    text: str
    severity: Severity = "medium"
    detector: DetectorKind = "rules"


# --------------------------------------------------------------------------
# claim building blocks
# --------------------------------------------------------------------------
class LandExtent(Base):
    value: float
    unit: str
    hectares: float


class Location(Base):
    village: Optional[str] = None
    taluk: Optional[str] = None
    district: Optional[str] = None
    state: str = "Tamil Nadu"
    lat: Optional[float] = None
    lon: Optional[float] = None
    resolution_confidence: float = 0.0
    resolved_by: Optional[str] = None
    citation_id: Optional[str] = None


class WeatherDay(Base):
    date: str
    precipitation_mm: float = 0.0
    wind_gust_kmh: float = 0.0
    temp_max_c: float = 0.0
    # snapshot extras beyond the contract minimum; kept so the chart can use them
    precipitation_hours: Optional[float] = None
    wind_speed_kmh: Optional[float] = None


class DateWindow(Base):
    start: str = ""
    end: str = ""


class WeatherEvidence(Base):
    source: Literal["snapshot", "none"] = "none"
    request_url: Optional[str] = None
    fetched_at: Optional[str] = None
    window: DateWindow = Field(default_factory=DateWindow)
    daily: list[WeatherDay] = Field(default_factory=list)
    context_30d_rain_mm: Optional[float] = None
    # mostly numeric, but the weather service reports `district_used` as a name
    metrics: dict[str, float | str] = Field(default_factory=dict)
    verdict: Verdict = "unverifiable"
    reasons: list[str] = Field(default_factory=list)
    farmer_sentence: str = ""
    nearby_matching_dates: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class DisasterEvent(Base):
    id: str
    type: str = ""
    name: str = ""
    alert_level: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""
    distance_km: Optional[float] = None
    report_url: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None

    model_config = ConfigDict(extra="ignore", populate_by_name=True, serialize_by_alias=True)


class DisasterEvidence(Base):
    source: Literal["gdacs", "none"] = "none"
    fetched_at: Optional[str] = None
    events: list[DisasterEvent] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class CropWindow(Base):
    sowing: str = ""
    harvest: str = ""


class CropEvidence(Base):
    crop: str = ""
    district: Optional[str] = None
    season: Optional[str] = None
    in_window: Optional[bool] = None
    window: Optional[CropWindow] = None
    note: str = ""
    citations: list[Citation] = Field(default_factory=list)


class SchemeMatch(Base):
    fact_id: str
    scheme: str = ""
    field: str = ""
    text: str = ""
    citation: Citation


class EvidenceItem(Base):
    key: str
    label: str
    label_local: Optional[str] = None
    instructions_local: Optional[str] = None
    why: str = ""
    citation_id: Optional[str] = None
    required: bool = True


class EvidenceFile(Base):
    id: str
    item_key: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    client_time: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    url: str
    quality_flag: QualityFlag = "unchecked"


class RiskSignal(Base):
    code: str
    description: str
    weight: int = 0


class Risk(Base):
    score: int = 0
    level: RiskLevel = "low"
    signals: list[RiskSignal] = Field(default_factory=list)


class Farmer(Base):
    name: Optional[str] = None
    phone: Optional[str] = None
    language: str = "en"


class AgentSaidFact(Base):
    fact_id: str
    verified: bool = False


# --------------------------------------------------------------------------
# top-level records
# --------------------------------------------------------------------------
class CallRecord(Base):
    id: int
    snapserve_call_id: str
    direction: CallDirection = "inbound"
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    status: CallStatus = "completed"
    started_at: str
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    language_detected: Optional[str] = None
    languages: list[str] = Field(default_factory=list)
    code_switching: bool = False
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    claim_id: Optional[int] = None
    ticket_id: Optional[int] = None
    guardrail_incidents: list[GuardrailIncident] = Field(default_factory=list)
    processing: ProcessingState = "pending"
    processing_error: Optional[str] = None


class Claim(Base):
    id: int
    reference: str
    call_id: int
    status: ClaimStatus = "logged"
    farmer: Farmer = Field(default_factory=Farmer)
    crop: Optional[str] = None
    land_extent: Optional[LandExtent] = None
    damage_type: Optional[str] = None
    event_date: Optional[str] = None
    event_date_confidence: float = 0.0
    location: Location = Field(default_factory=Location)
    narrative: str = ""
    weather_evidence: WeatherEvidence = Field(default_factory=WeatherEvidence)
    disaster_evidence: DisasterEvidence = Field(default_factory=DisasterEvidence)
    crop_evidence: Optional[CropEvidence] = None
    scheme_matches: list[SchemeMatch] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence_required: list[EvidenceItem] = Field(default_factory=list)
    evidence_uploads: list[EvidenceFile] = Field(default_factory=list)
    risk: Risk = Field(default_factory=Risk)
    escalation_reason: Optional[str] = None
    farmer_explanation: Optional[str] = None
    reviewer_notes: Optional[str] = None
    created_at: str
    updated_at: str
    agent_said_facts: list[AgentSaidFact] = Field(default_factory=list)


class Ticket(Base):
    id: int
    claim_id: int
    call_id: int
    reference: str
    severity: Severity = "medium"
    reasons: list[str] = Field(default_factory=list)
    farmer_explanation: str = ""
    status: TicketStatus = "open"
    reviewer_notes: Optional[str] = None
    created_at: str
    updated_at: str


class SnapshotDistrict(Base):
    name: str
    lat: float
    lon: float
    source_url: str = ""
    daily: list[WeatherDay] = Field(default_factory=list)
    notable: list[str] = Field(default_factory=list)


class WeatherSnapshot(Base):
    generated_at: str = ""
    days: int = 0
    coverage: Optional[DateWindow] = None
    districts: list[SnapshotDistrict] = Field(default_factory=list)
    disasters: list[DisasterEvent] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# --------------------------------------------------------------------------
# eval (implemented by a later worker; shapes fixed here)
# --------------------------------------------------------------------------
class EvalScenarioResult(Base):
    scenario: str
    language: str
    passed: bool = False
    promise_leaks: int = 0
    fabrications: int = 0
    escalation_ok: bool = True
    one_question_rate: float = 0.0
    transcript: list[TranscriptTurn] = Field(default_factory=list)


class EvalTotals(Base):
    promise_leaks: int = 0
    fabrications: int = 0
    escalation_failures: int = 0
    pass_rate: float = 0.0


class EvalReport(Base):
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    n_calls: int = 0
    languages: list[str] = Field(default_factory=list)
    results: list[EvalScenarioResult] = Field(default_factory=list)
    totals: EvalTotals = Field(default_factory=EvalTotals)


# --------------------------------------------------------------------------
# API request / response envelopes
# --------------------------------------------------------------------------
class PollerStatus(Base):
    running: bool = False
    last_poll_at: Optional[str] = None
    last_error: Optional[str] = None
    polls: int = 0


class HealthResponse(Base):
    ok: bool = True
    version: str
    snapserve_ok: bool = False
    gemini_ok: bool = False
    poller: PollerStatus = Field(default_factory=PollerStatus)
    data_down_mode: bool = False


class HourBucket(Base):
    hour: str
    calls: int


class StatsResponse(Base):
    calls_total: int = 0
    claims_total: int = 0
    tickets_open: int = 0
    guardrail_incidents: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    verdicts: dict[str, int] = Field(default_factory=dict)
    last_24h: list[HourBucket] = Field(default_factory=list)


class ClaimPatch(Base):
    status: Optional[ClaimStatus] = None
    reviewer_notes: Optional[str] = None


class TicketPatch(Base):
    status: Optional[TicketStatus] = None
    reviewer_notes: Optional[str] = None


class SimulateRequest(Base):
    transcript: str
    from_number: Optional[str] = None
    language: Optional[str] = None


class DataDownRequest(Base):
    enabled: bool


class EvidenceLinkResponse(Base):
    token: str
    url: str
    qr_svg: str
    whatsapp_url: str
    expires_at: str


class EvidenceChecklistItem(Base):
    key: str
    label: str
    label_local: Optional[str] = None
    instructions_local: Optional[str] = None
    required: bool = True
    uploaded: list[EvidenceFile] = Field(default_factory=list)


class EvidencePage(Base):
    claim_reference: str
    farmer_language: str = "en"
    items: list[EvidenceChecklistItem] = Field(default_factory=list)
    expires_at: str


class KnowledgeStatus(Base):
    last_refresh_at: Optional[str] = None
    agent_synced_at: Optional[str] = None
    districts: int = 0
    days: int = 0
    notable_events: int = 0
    approx_tokens: int = 0
    sources: list[Citation] = Field(default_factory=list)


class PromptResponse(Base):
    system_prompt: str
    approx_tokens: int


class EvalRunRequest(Base):
    scenarios: Optional[list[str]] = None
    n: Optional[int] = None


class Event(Base):
    type: str
    at: str
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# LLM extraction schema (used as a Gemini response_schema)
# --------------------------------------------------------------------------
class ExtractedContradiction(Base):
    text: str = ""
    why: str = ""


class CallExtraction(Base):
    """What the extractor pulls out of one transcript."""

    farmer_name: Optional[str] = None
    farmer_phone: Optional[str] = None
    language: str = "en"
    languages: list[str] = Field(default_factory=list)
    code_switching: bool = False
    crop: Optional[str] = None
    land_extent_value: Optional[float] = None
    land_extent_unit: Optional[str] = None
    damage_type: Optional[str] = None
    event_date: Optional[str] = None
    event_date_confidence: float = 0.0
    village: Optional[str] = None
    taluk: Optional[str] = None
    district: Optional[str] = None
    state: str = "Tamil Nadu"
    narrative: str = ""
    summary: str = ""
    distress: bool = False
    asked_for_human: bool = False
    outcome_questions_asked: list[str] = Field(default_factory=list)
    agent_quoted_facts: list[str] = Field(default_factory=list)
    agent_listed_evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class AuditIncident(Base):
    quote: str = ""
    category: GuardrailCategory = "other"
    severity: Severity = "medium"


class AuditResult(Base):
    incidents: list[AuditIncident] = Field(default_factory=list)


class TranslatedItem(Base):
    key: str
    label_local: str = ""
    instructions_local: str = ""


class TranslationResult(Base):
    items: list[TranslatedItem] = Field(default_factory=list)


# --------------------------------------------------------------------------
# interop helpers
# --------------------------------------------------------------------------
T = TypeVar("T", bound=BaseModel)


def to_plain(obj: Any) -> Any:
    """Best-effort conversion of a sibling worker's object into JSON-ish data."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    if hasattr(obj, "dict") and callable(obj.dict):  # pydantic v1 style
        try:
            return obj.dict()
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(obj, "__dict__"):
        return {k: to_plain(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def coerce(model: type[T], obj: Any, default: Optional[T] = None) -> T:
    """Validate ``obj`` into ``model``, falling back to ``default`` on failure."""
    if isinstance(obj, model):
        return obj
    try:
        return model.model_validate(to_plain(obj))
    except Exception:
        if default is not None:
            return default
        return model.model_construct()


def coerce_list(model: type[T], items: Any) -> list[T]:
    if not items:
        return []
    if not isinstance(items, (list, tuple)):
        items = [items]
    out: list[T] = []
    for item in items:
        try:
            out.append(coerce(model, item))
        except Exception:  # pragma: no cover - defensive
            continue
    return out


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
