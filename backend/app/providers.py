"""Adapter layer over the data / schemes workers' service modules.

Every call is a *late* import by the exact signature in ``docs/CONTRACTS.md``.
If a module has not landed yet (the workers build in parallel) we log one
warning and return a safe, honest fallback — ``unverifiable`` or empty, never a
fabricated "verified".  When the real module appears the next call picks it up
automatically; nothing here is cached across failures.
"""

from __future__ import annotations

import importlib
import json
import logging
from typing import Any, Callable, Optional

from app.config import settings
from app.schemas import (
    Citation,
    CropEvidence,
    DisasterEvidence,
    EvidenceItem,
    LandExtent,
    Location,
    SchemeMatch,
    WeatherEvidence,
    WeatherSnapshot,
    coerce,
    coerce_list,
)

logger = logging.getLogger(__name__)

_warned: set[str] = set()

# Fallback unit table (hectares per unit) — only used while services/crops.py
# is absent; the crops worker's table is authoritative once it lands.
_FALLBACK_UNITS: dict[str, float] = {
    "hectare": 1.0,
    "hectares": 1.0,
    "ha": 1.0,
    "acre": 0.404686,
    "acres": 0.404686,
    "cent": 0.00404686,
    "cents": 0.00404686,
    "bigha": 0.2529,
    "guntha": 0.010117,
    "kani": 0.5333,
    "ma": 0.0333,
    "ground": 0.0223,
}

_FALLBACK_CHECKLIST = [
    ("damage_photos", "Photos of the damaged crop (3 angles)", True,
     "Shows the extent and nature of the damage in the field."),
    ("land_record", "Land record (chitta / patta / adangal)", True,
     "Proves the land is yours and gives the surveyed extent."),
    ("sowing_proof", "Sowing proof (seed bill or sowing certificate)", True,
     "Shows the crop was sown in this season."),
    ("bank_passbook", "Bank passbook first page", True,
     "Needed so any assessed amount reaches the right account."),
    ("id_proof", "ID proof (Aadhaar with the number masked)", False,
     "Confirms identity; mask all but the last four digits."),
]

_FALLBACK_SAFE_SCRIPTS = {
    "payout_question": {
        "en": "I cannot tell you any amount. The amount is decided later by the "
              "insurance company after a field survey. What I can do now is record "
              "your details correctly.",
    },
    "approval_question": {
        "en": "I cannot approve or reject anything, and I cannot promise approval. "
              "I record your claim and a reviewer checks it.",
    },
    "timeline_question": {
        "en": "I cannot promise a date. I will note your claim now and a reviewer "
              "will follow up with you.",
    },
    "escalation": {
        "en": "I am passing this to a person who will check it with you.",
    },
    "data_unavailable": {
        "en": "I could not check the records just now, so I will not guess. A person "
              "will verify this with you.",
    },
}


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(message, *args)


def _load(module_name: str, attr: str) -> Optional[Callable[..., Any]]:
    """Import ``services.<module_name>.<attr>``; None (with one warning) if absent."""
    try:
        module = importlib.import_module(f"services.{module_name}")
    except ImportError:
        _warn_once(f"mod:{module_name}", "services.%s not available yet — using fallback", module_name)
        return None
    except Exception as exc:  # pragma: no cover - a broken sibling module
        _warn_once(f"broken:{module_name}", "services.%s failed to import: %s", module_name, exc)
        return None
    func = getattr(module, attr, None)
    if func is None:
        _warn_once(f"attr:{module_name}.{attr}", "services.%s has no %s() — using fallback", module_name, attr)
        return None
    return func


def module_status() -> dict[str, bool]:
    """Which sibling modules are importable right now (for /api/health)."""
    status: dict[str, bool] = {}
    for name in ("gazetteer", "weather", "disasters", "crops", "schemes", "knowledge_weather"):
        try:
            importlib.import_module(f"services.{name}")
            status[name] = True
        except Exception:
            status[name] = False
    return status


# --------------------------------------------------------------------------
# gazetteer
# --------------------------------------------------------------------------
def resolve_location(
    village: str | None,
    taluk: str | None,
    district: str | None,
    state: str = "Tamil Nadu",
) -> Location:
    func = _load("gazetteer", "resolve_location")
    if func is not None:
        try:
            return coerce(Location, func(village, taluk, district, state))
        except Exception as exc:
            logger.warning("resolve_location failed: %s", exc)
    return Location(
        village=village,
        taluk=taluk,
        district=district,
        state=state or "Tamil Nadu",
        resolution_confidence=0.0,
        resolved_by="unresolved",
    )


def list_districts() -> list[dict]:
    func = _load("gazetteer", "list_districts")
    if func is not None:
        try:
            return list(func())
        except Exception as exc:
            logger.warning("list_districts failed: %s", exc)
    return []


# --------------------------------------------------------------------------
# weather / disasters
# --------------------------------------------------------------------------
def check_weather(
    lat: float | None,
    lon: float | None,
    event_date: str | None,
    damage_type: str | None,
    *,
    data_down: bool = False,
) -> WeatherEvidence:
    unverifiable = WeatherEvidence(
        source="none",
        verdict="unverifiable",
        reasons=["weather snapshot unavailable"],
        farmer_sentence=(
            "I could not check the weather record for that day, so a person will "
            "verify it with you."
        ),
    )
    if lat is None or lon is None or not event_date:
        unverifiable.reasons = ["location or event date missing — nothing to check against"]
        return unverifiable
    func = _load("weather", "check_weather")
    if func is None:
        return unverifiable
    try:
        return coerce(
            WeatherEvidence,
            func(lat, lon, event_date, damage_type or "other", data_down=data_down),
            default=unverifiable,
        )
    except Exception as exc:
        logger.warning("check_weather failed: %s", exc)
        unverifiable.reasons = [f"weather check error: {exc.__class__.__name__}"]
        return unverifiable


def check_disasters(
    lat: float | None,
    lon: float | None,
    event_date: str | None,
    *,
    radius_km: float = 300,
    days: int = 5,
    data_down: bool = False,
) -> DisasterEvidence:
    empty = DisasterEvidence(source="none")
    if lat is None or lon is None or not event_date:
        return empty
    func = _load("disasters", "check_disasters")
    if func is None:
        return empty
    try:
        return coerce(
            DisasterEvidence,
            func(lat, lon, event_date, radius_km=radius_km, days=days, data_down=data_down),
            default=empty,
        )
    except Exception as exc:
        logger.warning("check_disasters failed: %s", exc)
        return empty


def load_snapshot() -> Optional[WeatherSnapshot]:
    func = _load("knowledge_weather", "load_snapshot")
    if func is not None:
        try:
            return coerce(WeatherSnapshot, func())
        except Exception as exc:
            logger.warning("load_snapshot failed: %s", exc)
    # direct read of the snapshot file as a last resort
    path = settings.weather_snapshot_path
    if path.exists():
        try:
            return WeatherSnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("weather_snapshot.json unreadable: %s", exc)
    return None


def render_weather_knowledge(snapshot: WeatherSnapshot | None = None) -> str:
    """Prompt text for the weather block.

    The snapshot is re-loaded through the data worker's own loader so its native
    model (which carries fields beyond the contract minimum) reaches the renderer
    intact — passing our coerced copy would strip them.
    """
    render = _load("knowledge_weather", "render_weather_knowledge")
    native_loader = _load("knowledge_weather", "load_snapshot")
    if render is None:
        return ""
    try:
        native = native_loader() if native_loader is not None else snapshot
        if native is None:
            return ""
        return str(render(native))
    except Exception as exc:
        logger.warning("render_weather_knowledge failed: %s", exc)
        return ""


# --------------------------------------------------------------------------
# crops
# --------------------------------------------------------------------------
def check_crop_window(
    crop: str | None, district: str | None, event_date: str | None
) -> Optional[CropEvidence]:
    if not crop or not event_date:
        return None
    func = _load("crops", "check_crop_window")
    if func is None:
        return CropEvidence(
            crop=crop,
            district=district,
            in_window=None,
            note="Crop calendar not available; the sowing window was not checked.",
        )
    try:
        return coerce(CropEvidence, func(crop, district, event_date))
    except Exception as exc:
        logger.warning("check_crop_window failed: %s", exc)
        return CropEvidence(crop=crop, district=district, in_window=None, note="Crop window check failed.")


def normalize_crop(text: str | None) -> Optional[str]:
    if not text:
        return None
    func = _load("crops", "normalize_crop")
    if func is not None:
        try:
            result = func(text)
            if result:
                return str(result)
        except Exception as exc:
            logger.warning("normalize_crop failed: %s", exc)
    return text.strip().lower() or None


def normalize_land_extent(value: float | None, unit_text: str | None) -> Optional[LandExtent]:
    if value is None:
        return None
    unit = (unit_text or "acre").strip().lower()
    func = _load("crops", "normalize_land_extent")
    if func is not None:
        try:
            return coerce(LandExtent, func(value, unit))
        except Exception as exc:
            logger.warning("normalize_land_extent failed: %s", exc)
    factor = _FALLBACK_UNITS.get(unit, _FALLBACK_UNITS.get(unit.rstrip("s"), 0.404686))
    return LandExtent(value=float(value), unit=unit, hectares=round(float(value) * factor, 4))


def crop_calendar_text(max_rows: int = 120) -> str:
    """Compact render of ``data/crop_calendar_tn.json`` for the prompt."""
    path = settings.data_dir / "crop_calendar_tn.json"
    if not path.exists():
        _warn_once("cropcal", "crop_calendar_tn.json not present yet — prompt section will be empty")
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("crop_calendar_tn.json unreadable: %s", exc)
        return ""
    rows = raw.get("rows") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return ""
    lines: list[str] = []
    for row in rows[:max_rows]:
        if not isinstance(row, dict):
            continue
        district = row.get("district") or row.get("District") or "TN"
        crop = row.get("crop") or row.get("Crop") or "?"
        season = row.get("season") or row.get("Season") or ""
        sowing = row.get("sowing") or row.get("sowing_window") or ""
        harvest = row.get("harvest") or row.get("harvest_window") or ""
        cid = row.get("citation_id") or row.get("id") or ""
        tag = f" [{cid}]" if cid else ""
        lines.append(f"- {district} | {crop} | {season}: sowing {sowing}, harvest {harvest}{tag}")
    if len(rows) > max_rows:
        lines.append(f"- (+{len(rows) - max_rows} more district/crop rows on file)")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# schemes
# --------------------------------------------------------------------------
def lookup_scheme(
    crop: str | None,
    district: str | None,
    event_date: str | None,
    damage_type: str | None,
) -> tuple[list[SchemeMatch], list[str]]:
    func = _load("schemes", "lookup_scheme")
    if func is None:
        return [], ["Scheme facts are not loaded, so no scheme detail was quoted."]
    try:
        result = func(crop, district, event_date, damage_type)
        if isinstance(result, tuple) and len(result) == 2:
            matches, unknowns = result
        else:  # tolerate a bare list
            matches, unknowns = result, []
        return coerce_list(SchemeMatch, matches), [str(u) for u in (unknowns or [])]
    except Exception as exc:
        logger.warning("lookup_scheme failed: %s", exc)
        return [], ["Scheme lookup failed; nothing was quoted."]


def evidence_checklist(damage_type: str | None, crop: str | None) -> list[EvidenceItem]:
    func = _load("schemes", "evidence_checklist")
    if func is not None:
        try:
            items = coerce_list(EvidenceItem, func(damage_type, crop))
            if items:
                return items
        except Exception as exc:
            logger.warning("evidence_checklist failed: %s", exc)
    return [
        EvidenceItem(key=key, label=label, required=required, why=why)
        for key, label, required, why in _FALLBACK_CHECKLIST
    ]


def render_scheme_knowledge() -> str:
    func = _load("schemes", "render_scheme_knowledge")
    if func is not None:
        try:
            return str(func())
        except Exception as exc:
            logger.warning("render_scheme_knowledge failed: %s", exc)
    return ""


def safe_scripts() -> dict:
    func = _load("schemes", "safe_scripts")
    if func is not None:
        try:
            scripts = func()
            if scripts:
                return dict(scripts)
        except Exception as exc:
            logger.warning("safe_scripts failed: %s", exc)
    path = settings.data_dir / "safe_scripts.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("safe_scripts.json unreadable: %s", exc)
    return dict(_FALLBACK_SAFE_SCRIPTS)


def load_facts() -> list[dict]:
    func = _load("schemes", "load_facts")
    if func is not None:
        try:
            return list(func())
        except Exception as exc:
            logger.warning("load_facts failed: %s", exc)
    return []


def citation_by_id(cid: str) -> Optional[Citation]:
    func = _load("schemes", "citation_by_id")
    if func is not None:
        try:
            found = func(cid)
            if found is not None:
                return coerce(Citation, found)
        except Exception as exc:
            logger.warning("citation_by_id failed: %s", exc)
    return None


def known_citation_ids() -> set[str]:
    """Every citation id the agent is allowed to quote."""
    ids: set[str] = set()
    for fact in load_facts():
        if isinstance(fact, dict):
            if fact.get("id"):
                ids.add(str(fact["id"]))
            citation = fact.get("citation")
            if isinstance(citation, dict) and citation.get("id"):
                ids.add(str(citation["id"]))
    snapshot = load_snapshot()
    if snapshot is not None:
        for citation in snapshot.citations:
            ids.add(citation.id)
        for district in snapshot.districts:
            ids.update(district.notable)
        for disaster in snapshot.disasters:
            ids.add(f"D-{disaster.id}")
    return ids
