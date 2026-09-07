"""Crop name normalisation, land-extent conversion and the TN crop calendar.

Fully offline. The calendar in ``backend/data/crop_calendar_tn.json`` was built
once from the Tamil Nadu Season and Crop Report (Table X) and the PMFBY district
crop calendar; nothing here fetches anything.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from .models import Citation, CropEvidence, CropWindow, LandExtent

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CALENDAR_PATH = DATA_DIR / "crop_calendar_tn.json"

#: rapidfuzz floor for accepting a fuzzy crop-name match.
CROP_MATCH_THRESHOLD = 86

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

__all__ = [
    "normalize_crop",
    "normalize_land_extent",
    "check_crop_window",
    "crop_calendar_citation",
    "render_crop_calendar",
    "CROP_NAMES",
    "LAND_UNITS",
]

# --------------------------------------------------------------------------- #
# crop names
# --------------------------------------------------------------------------- #
#: Canonical crop -> spoken names across Tamil, Hindi, Telugu, Kannada,
#: Malayalam, Marathi and English (romanised as a caller would say them).
CROP_NAMES: dict[str, list[str]] = {
    "paddy": [
        "paddy", "rice", "nel", "nellu", "arisi", "vari", "dhan", "dhaan",
        "chawal", "biyyam", "vadlu", "akki", "bhat", "ari", "nel pyir",
        "samba", "kuruvai", "navarai", "sornavari", "thaladi", "pishanam",
    ],
    "groundnut": [
        "groundnut", "peanut", "verkadalai", "kadalai", "nilakadalai",
        "mungfali", "moongphali", "palli", "pallilu", "verusenaga",
        "kadalekai", "shengdana", "kappalandi", "nelakadala",
    ],
    "sugarcane": [
        "sugarcane", "cane", "karumbu", "ganna", "cheruku", "kabbu", "us",
        "karimbu", "sakkarai karumbu",
    ],
    "cotton": [
        "cotton", "paruthi", "parutti", "kapas", "patti", "hatti", "pathi",
        "prathi", "panju",
    ],
    "maize": [
        "maize", "corn", "makkacholam", "maka cholam", "makka", "makkai",
        "makkacholam pyir", "mokkajonna", "musukina jola", "cholam maize",
        "bhutta", "makka jola",
    ],
    "black_gram": [
        "black gram", "blackgram", "urad", "urad dal", "ulundu", "ulunthu",
        "minumu", "minumulu", "uddu", "uddina bele", "udid", "uzhunnu",
    ],
    "green_gram": [
        "green gram", "greengram", "moong", "mung", "pachai payaru",
        "pasi payaru", "payaru", "pesalu", "hesaru", "cherupayar", "mug",
    ],
    "red_gram": [
        "red gram", "redgram", "pigeon pea", "thuvarai", "thuvaram paruppu",
        "arhar", "tur", "toor", "kandi", "kandulu", "togari", "thuvara",
    ],
    "banana": [
        "banana", "plantain", "vazhai", "vaazhai", "kela", "arati", "aratipandu",
        "baale", "balehannu", "vaazhaipazham", "nendran",
    ],
    "turmeric": [
        "turmeric", "manjal", "haldi", "pasupu", "arishina", "manjalu",
        "halad", "manjaḷ",
    ],
    "chilli": [
        "chilli", "chili", "chillies", "milagai", "molagai", "mirchi", "mirch",
        "mirapa", "mirapakaya", "menasina", "menasinakayi", "mulaku", "mirchi kaay",
    ],
    "tomato": [
        "tomato", "thakkali", "takkali", "tamatar", "tamota", "tomato pandu",
        "tomatohannu",
    ],
    "onion": [
        "onion", "vengayam", "venkayam", "pyaz", "piyaz", "ulli", "nirulli",
        "eerulli", "ullipaya", "kanda", "chinna vengayam",
    ],
    "coconut": [
        "coconut", "thengai", "thenga", "nariyal", "kobbari", "tenginakayi",
        "naral", "kobbari kaya",
    ],
    "ragi": [
        "ragi", "finger millet", "kezhvaragu", "kelvaragu", "keppai", "ragulu",
        "nachni", "moothari", "raagi",
    ],
    "bajra": [
        "bajra", "pearl millet", "kambu", "cumbu", "sajja", "sajjalu", "sajje",
        "kambam", "bajri",
    ],
    "jowar": [
        "jowar", "sorghum", "cholam", "solam", "jonna", "jonnalu", "jola",
        "jwari", "cholam pyir",
    ],
    "sesame": [
        "sesame", "gingelly", "till", "til", "ellu", "nuvvulu", "nuvvu",
        "yellu", "ellu vithai", "tila", "sesamum",
    ],
    "tapioca": [
        "tapioca", "cassava", "maravalli", "maravalli kizhangu", "kappa",
        "karapendalam", "mara genasu", "sabudana plant",
    ],
    "brinjal": [
        "brinjal", "eggplant", "aubergine", "kathirikai", "kathrikai", "baingan",
        "vankaya", "badanekai", "vazhuthana", "vange",
    ],
    "okra": [
        "okra", "ladies finger", "lady finger", "vendakkai", "vendaikai",
        "bhindi", "bendakaya", "bendekayi", "venda", "bhendi",
    ],
    "mango": [
        "mango", "maa", "mangai", "maampazham", "aam", "mamidi", "mamidikaya",
        "mavinakayi", "manga", "amba",
    ],
}

_CROP_LOOKUP: dict[str, str] = {}
for _canonical, _names in CROP_NAMES.items():
    _CROP_LOOKUP[_canonical] = _canonical
    for _name in _names:
        _CROP_LOOKUP[_name.lower()] = _canonical


def _clean(text: str | None) -> str:
    """Lower-case, drop punctuation and common filler words."""
    if not text:
        return ""
    out = re.sub(r"[^a-z0-9 ]+", " ", text.strip().lower())
    out = re.sub(r"\b(crop|pyir|payir|farming|cultivation|field|my|the)\b", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def normalize_crop(text: str) -> str | None:
    """Map a spoken crop name in any language to its canonical English name.

    Args:
        text: What the caller said, romanised (e.g. ``"nel"``, ``"mungfali"``).

    Returns:
        A canonical name such as ``"paddy"``, or ``None`` when nothing matched
        confidently. Never guesses.
    """
    key = _clean(text)
    if not key:
        return None
    if key in _CROP_LOOKUP:
        return _CROP_LOOKUP[key]
    for word in key.split():
        if word in _CROP_LOOKUP:
            return _CROP_LOOKUP[word]
    hit = process.extractOne(key, list(_CROP_LOOKUP), scorer=fuzz.WRatio)
    if hit and hit[1] >= CROP_MATCH_THRESHOLD:
        return _CROP_LOOKUP[hit[0]]
    logger.info("Unrecognised crop name %r", text)
    return None


# --------------------------------------------------------------------------- #
# land extent
# --------------------------------------------------------------------------- #
#: Unit name (and spoken variants) -> hectares per unit, plus an optional note.
LAND_UNITS: dict[str, tuple[float, str, str]] = {
    # spoken key: (hectares per unit, canonical unit, note)
    "hectare": (1.0, "hectare", ""),
    "hectares": (1.0, "hectare", ""),
    "ha": (1.0, "hectare", ""),
    "hektar": (1.0, "hectare", ""),
    "acre": (0.404686, "acre", ""),
    "acres": (0.404686, "acre", ""),
    "ekkar": (0.404686, "acre", ""),
    "ekar": (0.404686, "acre", ""),
    "cent": (0.00404686, "cent", ""),
    "cents": (0.00404686, "cent", ""),
    "sent": (0.00404686, "cent", ""),
    "bigha": (
        0.25,
        "bigha",
        "A bigha is not a fixed size; 0.25 ha is a common average, so this "
        "figure needs confirming with the land record.",
    ),
    "biga": (0.25, "bigha", "A bigha is not a fixed size; 0.25 ha is a common average."),
    "guntha": (0.0101, "guntha", ""),
    "gunta": (0.0101, "guntha", ""),
    "kani": (0.534, "kani", "One kani is taken as 1.32 acres (Tamil Nadu usage)."),
    "kaani": (0.534, "kani", "One kani is taken as 1.32 acres (Tamil Nadu usage)."),
    "ma": (0.134, "ma", "One ma is a quarter kani (about a third of an acre)."),
    "maa": (0.134, "ma", "One ma is a quarter kani (about a third of an acre)."),
    "ground": (0.0223, "ground", "One ground is 2400 square feet."),
    "grounds": (0.0223, "ground", "One ground is 2400 square feet."),
    "sq ft": (9.2903e-6, "sq ft", ""),
    "sqft": (9.2903e-6, "sq ft", ""),
    "square feet": (9.2903e-6, "sq ft", ""),
    "square foot": (9.2903e-6, "sq ft", ""),
    "sq m": (1e-4, "sq m", ""),
    "square metre": (1e-4, "sq m", ""),
}


def normalize_land_extent(value: float, unit_text: str) -> LandExtent:
    """Convert a spoken land area to hectares.

    Args:
        value: The number the caller gave.
        unit_text: The unit as spoken ("acre", "cent", "bigha", "kani", ...).

    Returns:
        A :class:`~services.models.LandExtent`. An unrecognised unit keeps the
        value, reports ``unit="unknown"`` and ``hectares=0.0`` so no downstream
        arithmetic silently invents an area.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    key = _clean(unit_text)
    entry = LAND_UNITS.get(key)
    if entry is None and key:
        hit = process.extractOne(key, list(LAND_UNITS), scorer=fuzz.WRatio)
        if hit and hit[1] >= 88:
            entry = LAND_UNITS[hit[0]]
    if entry is None:
        logger.info("Unrecognised land unit %r", unit_text)
        return LandExtent(value=number, unit="unknown", hectares=0.0)
    per_unit, canonical, _note = entry
    return LandExtent(
        value=number, unit=canonical, hectares=round(number * per_unit, 4)
    )


# --------------------------------------------------------------------------- #
# crop calendar
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _calendar() -> dict:
    """Cached read of ``backend/data/crop_calendar_tn.json``."""
    with CALENDAR_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _md(value: str) -> int:
    """``"05-01"`` -> 501, so month-day ranges compare as plain integers."""
    month, day = value.split("-")
    return int(month) * 100 + int(day)


def _in_range(point: int, start: int, end: int) -> bool:
    """Month-day containment that copes with windows crossing 31 December."""
    if start <= end:
        return start <= point <= end
    return point >= start or point <= end


def _pretty(start: str, end: str) -> str:
    a, b = int(start[:2]), int(end[:2])
    return MONTH_NAMES[a] if a == b else f"{MONTH_NAMES[a]}-{MONTH_NAMES[b]}"


def crop_calendar_citation(cid: str) -> Citation | None:
    """Resolve a ``C-<n>`` crop-calendar citation id."""
    for entry in _calendar()["entries"]:
        if entry["id"] == cid:
            return Citation(**entry["citation"])
    return None


def _entries_for(crop: str, district: str | None) -> list[dict]:
    """Calendar entries for a crop, narrowed to a district when one is known."""
    rows = [e for e in _calendar()["entries"] if e["crop"] == crop]
    if not district:
        return rows
    named = [
        e for e in rows if e["district"] == "ALL" or district in e["districts"]
    ]
    return named


def check_crop_window(crop: str, district: str | None, event_date: str) -> CropEvidence:
    """Was this crop plausibly standing in the field on this date?

    "In window" means the date falls between the start of sowing and the end of
    harvest for at least one recorded season, which is when damage to a standing
    crop is possible.

    Args:
        crop: Crop name in any language; normalised internally.
        district: Official Tamil Nadu district name, or ``None``.
        event_date: ISO date of the reported damage.

    Returns:
        A :class:`~services.models.CropEvidence`. ``in_window`` is ``None``
        whenever the calendar simply has nothing to say.
    """
    canonical = normalize_crop(crop) or ""
    if not canonical:
        return CropEvidence(
            crop=crop,
            district=district,
            in_window=None,
            note=(
                f"'{crop}' is not a crop name I recognise, so I cannot check the "
                "sowing and harvest window for it."
            ),
        )

    try:
        point = _md(date.fromisoformat(event_date).strftime("%m-%d"))
    except (TypeError, ValueError):
        return CropEvidence(
            crop=canonical,
            district=district,
            in_window=None,
            note=f"Could not read {event_date!r} as a date, so no crop window was checked.",
        )

    rows = _entries_for(canonical, district)
    if not rows:
        scope = f"in {district}" if district else "in Tamil Nadu"
        return CropEvidence(
            crop=canonical,
            district=district,
            in_window=None,
            note=(
                f"The crop calendar has no row for {canonical.replace('_', ' ')} "
                f"{scope}, so I cannot say whether it would have been in the field "
                f"on {event_date}."
            ),
            citations=[c for c in (_source_citation(),) if c],
        )

    hits = [
        e
        for e in rows
        if _in_range(point, _md(e["sowing_start"]), _md(e["harvest_end"]))
    ]
    chosen = hits[0] if hits else rows[0]
    window = CropWindow(
        sowing=_pretty(chosen["sowing_start"], chosen["sowing_end"]),
        harvest=_pretty(chosen["harvest_start"], chosen["harvest_end"]),
    )
    season = chosen["season"]
    if chosen["variant"] and chosen["variant"] != season:
        season = f"{season} ({chosen['variant']})"
    where = district or "Tamil Nadu"
    crop_label = canonical.replace("_", " ")

    if hits:
        note = (
            f"{crop_label} in {where} is sown around {window.sowing} and harvested "
            f"around {window.harvest} ({chosen['season']} season), so a crop standing "
            f"on {event_date} fits the calendar."
        )
        if len(hits) > 1:
            note += f" {len(hits)} recorded seasons cover this date."
    else:
        others = "; ".join(
            f"{_pretty(e['sowing_start'], e['sowing_end'])} to "
            f"{_pretty(e['harvest_start'], e['harvest_end'])}"
            for e in rows[:3]
        )
        note = (
            f"The calendar puts {crop_label} in {where} in the field around {others}. "
            f"{event_date} falls outside those windows, which is worth checking gently "
            "with the farmer - calendars are peak seasons, not hard limits."
        )

    citations = [Citation(**e["citation"]) for e in (hits or rows)[:3]]
    return CropEvidence(
        crop=canonical,
        district=district,
        season=season,
        in_window=bool(hits),
        window=window,
        note=note,
        citations=citations,
    )


def _source_citation() -> Citation | None:
    """The calendar's own top-level source, used when no entry matched."""
    sources = _calendar().get("sources") or []
    if not sources:
        return None
    return Citation(id="C-source", **sources[0])


# --------------------------------------------------------------------------- #
# prompt rendering
# --------------------------------------------------------------------------- #
#: Prompt render order, roughly by Tamil Nadu cropped area.
CROP_PRIORITY = [
    "paddy", "groundnut", "sugarcane", "cotton", "maize", "jowar", "bajra",
    "ragi", "black_gram", "green_gram", "red_gram", "sesame",
]


def render_crop_calendar(max_tokens: int = 2000) -> str:
    """Render the crop calendar as compact prompt text with ``[C-n]`` ids.

    Lines are emitted in crop-priority order, widest district group first, and
    stop once ``max_tokens`` (chars/4) would be exceeded; anything dropped is
    still checked server-side by :func:`check_crop_window`, and the closing line
    says so.

    Args:
        max_tokens: Approximate token budget for the returned text.

    Returns:
        Prompt-ready text.
    """
    calendar = _calendar()
    entries = calendar["entries"]
    order = {crop: i for i, crop in enumerate(CROP_PRIORITY)}
    ranked = sorted(
        entries,
        key=lambda e: (
            order.get(e["crop"], len(CROP_PRIORITY)),
            -len(e["districts"]),
            e["sowing_start"],
        ),
    )

    head = [
        f"Tamil Nadu crop calendar (peak sowing to peak harvest), as of "
        f"{calendar['as_of']}. Windows are whole months, not exact days, and are "
        "typical seasons rather than hard limits.",
        "Lines read: [id] <crop> <season> <sowing months> to <harvest months>: "
        "<districts>.",
        "",
    ]
    budget = max_tokens * 4 - sum(len(line) + 1 for line in head) - 240
    body: list[str] = []
    used = 0
    dropped = 0
    for entry in ranked:
        districts = "ALL" if entry["district"] == "ALL" else ", ".join(
            entry["districts"]
        )
        variant = (
            f" {entry['variant']}"
            if entry["variant"] and entry["variant"] != entry["season"]
            else ""
        )
        line = (
            f"[{entry['id']}] {entry['crop'].replace('_', ' ')} "
            f"{entry['season']}{variant} "
            f"{_pretty(entry['sowing_start'], entry['sowing_end'])} to "
            f"{_pretty(entry['harvest_start'], entry['harvest_end'])}: {districts}"
        )
        if used + len(line) + 1 > budget:
            dropped += 1
            continue
        body.append(line)
        used += len(line) + 1

    tail = [
        "",
        f"{len(body)} of {len(entries)} calendar windows are listed here"
        + (
            f"; {dropped} more district-specific windows exist and the desk checks "
            "them for you, so never say a crop is out of season on your own - ask "
            "the farmer and let the check answer."
            if dropped
            else "."
        ),
    ]
    return "\n".join(head + body + tail).rstrip() + "\n"
