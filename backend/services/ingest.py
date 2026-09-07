"""The ingest pipeline: one completed call -> one truth-checked claim.

Steps (see ``docs/CONTRACTS.md``):

1. tolerant transcript parsing + language / code-switch detection
2. Gemini extraction against a strict JSON schema (deterministic regex fallback
   when ``GEMINI_DISABLED`` is set, so the whole pipeline runs offline)
3. resolve_location -> check_weather -> check_disasters -> check_crop_window ->
   lookup_scheme -> evidence_checklist (all via :mod:`app.providers`)
4. risk scoring
5. guardrail audit (rules + judge) and the ``agent_said_facts`` cross-check
6. decision: claim logged, or escalated with a ticket

WS events are emitted as each block lands so the dashboard animates the facts
appearing: ``claim.created`` early with partial data, then ``claim.updated``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from app import providers
from app.config import settings
from app.db import (
    CallRow,
    ClaimRow,
    GuardrailIncidentRow,
    TicketRow,
    cache_citation,
    next_reference,
    now_iso,
    read_session,
    session_scope,
)
from app.events import emit
from app.schemas import (
    AgentSaidFact,
    CallExtraction,
    CallRecord,
    Claim,
    GuardrailIncident,
    Risk,
    RiskSignal,
    TranscriptTurn,
)
from app.serializers import call_to_schema, claim_summary, claim_to_schema, ticket_to_schema
from services import guardrail

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

ESCALATION_THRESHOLD = 40
LARGE_EXTENT_HECTARES = 20.0
LOCALIZED_CALAMITIES = {"hailstorm", "landslide", "inundation", "fire", "pest", "disease"}

DAMAGE_TYPES = [
    "cyclone", "flood", "inundation", "heavy_rain", "unseasonal_rain", "drought",
    "hailstorm", "pest", "disease", "fire", "landslide", "other",
]

# --------------------------------------------------------------------------
# 1. transcript parsing
# --------------------------------------------------------------------------
_AGENT_LABELS = ("agent", "assistant", "ai", "bot", "sunil", "system")
_CALLER_LABELS = ("caller", "user", "customer", "farmer", "human", "client")

_ROLE_LINE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z _-]{0,20}?)\s*[:>-]\s*(?P<text>.*)$"
)


def _role_for(label: str) -> Optional[str]:
    key = re.sub(r"[^a-z]", "", label.lower())
    if not key:
        return None
    for candidate in _AGENT_LABELS:
        if key.startswith(candidate):
            return "agent"
    for candidate in _CALLER_LABELS:
        if key.startswith(candidate):
            return "caller"
    return None


def parse_transcript(raw: str | None) -> list[TranscriptTurn]:
    """Parse SnapServe's transcript string into turns.

    Tolerant of: unlabelled continuation lines, ``Agent:``/``Caller:`` written
    without a following space, alternative labels, and blank lines.  The STT
    frequently drops spaces *inside* the text ("thisis Priyafrom") — that is left
    untouched here and handled by the extractors.
    """
    if not raw:
        return []
    turns: list[TranscriptTurn] = []
    for line in str(raw).replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        role: Optional[str] = None
        text = stripped
        match = _ROLE_LINE.match(stripped)
        if match:
            role = _role_for(match.group("label"))
            if role:
                text = match.group("text").strip()
        if role is None:
            if turns:
                # continuation of the previous speaker
                turns[-1].text = f"{turns[-1].text} {stripped}".strip()
                continue
            role = "caller"
        if not text:
            continue
        turns.append(TranscriptTurn(i=len(turns), role=role, text=text))
    return turns


def turns_text(turns: Iterable[TranscriptTurn], role: str | None = None) -> str:
    return "\n".join(t.text for t in turns if role is None or t.role == role)


def transcript_to_text(turns: Iterable[TranscriptTurn]) -> str:
    return "\n".join(
        f"{'Agent' if t.role == 'agent' else 'Caller'}: {t.text}" for t in turns
    )


# --------------------------------------------------------------------------
# 2. language detection
# --------------------------------------------------------------------------
_SCRIPT_RANGES: list[tuple[str, int, int]] = [
    ("ta", 0x0B80, 0x0BFF),
    ("hi", 0x0900, 0x097F),
    ("te", 0x0C00, 0x0C7F),
    ("kn", 0x0C80, 0x0CFF),
    ("ml", 0x0D00, 0x0D7F),
    ("bn", 0x0980, 0x09FF),
    ("gu", 0x0A80, 0x0AFF),
    ("pa", 0x0A00, 0x0A7F),
    ("or", 0x0B00, 0x0B7F),
]

_ROMANISED_MARKERS: dict[str, tuple[str, ...]] = {
    "ta": ("naan", "enakku", "illa", "mudiyathu", "vayal", "nel", "mazhai", "enna",
           "irukku", "panren", "kidaikkum", "nethu", "ungaluku", "sollunga"),
    "hi": ("mera", "mujhe", "nahi", "hai", "kya", "kaise", "barish", "fasal",
           "milega", "hua", "kisan", "khet"),
    "te": ("nenu", "naku", "ledu", "emi", "vastundi", "pantalu", "varsham", "rojullo"),
    "kn": ("nanu", "nanage", "illa", "yenu", "siguttade", "male", "belel"),
    "ml": ("njan", "enikku", "illa", "entha", "kittum", "mazha", "krishi"),
}


def _script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        code = ord(char)
        if code < 0x0900:
            if char.isalpha():
                counts["en"] = counts.get("en", 0) + 1
            continue
        for lang, low, high in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[lang] = counts.get(lang, 0) + 1
                break
    return counts


def detect_languages(turns: list[TranscriptTurn]) -> tuple[str, list[str], bool]:
    """(dominant language, languages used, code_switching) from caller turns."""
    text = turns_text(turns, "caller") or turns_text(turns)
    if not text.strip():
        return "en", [], False

    counts = _script_counts(text)
    native = {lang: n for lang, n in counts.items() if lang != "en" and n >= 3}
    latin = counts.get("en", 0)

    languages: list[str] = sorted(native, key=lambda k: native[k], reverse=True)

    lowered = text.lower()
    romanised: list[str] = []
    for lang, markers in _ROMANISED_MARKERS.items():
        hits = sum(1 for marker in markers if marker in lowered)
        if hits >= 2:
            romanised.append(lang)

    if latin >= 10:
        if romanised:
            for lang in romanised:
                if lang not in languages:
                    languages.append(lang)
            if not native:
                languages = romanised + (["en"] if latin > 60 else [])
        elif "en" not in languages:
            languages.append("en")

    if not languages:
        languages = ["en"]

    dominant = languages[0]
    code_switching = len(set(languages)) > 1 or bool(native and latin >= 15)
    return dominant, list(dict.fromkeys(languages)), code_switching


# --------------------------------------------------------------------------
# 3. deterministic extraction (offline fallback)
# --------------------------------------------------------------------------
_CROP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "paddy": ("paddy", "rice", "nel", "vari", "dhan", "chawal", "batta",
              "நெல்", "धान", "चावल", "వరి", "ಭತ್ತ", "നെല്ല"),
    "sugarcane": ("sugarcane", "karumbu", "ganna", "cheruku", "கரும்பு", "गन्ना", "చెరకు"),
    "banana": ("banana", "vazhai", "kela", "arati", "வாழை", "केला", "అరటి"),
    "groundnut": ("groundnut", "peanut", "kadalai", "moongphali", "நிலக்கடலை", "मूंगफली"),
    "cotton": ("cotton", "parutthi", "paruthi", "kapas", "பருத்தி", "कपास", "ಹತ್ತಿ"),
    "maize": ("maize", "corn", "makkacholam", "makka", "மக்காச்சோளம்", "मक्का", "మొక్కజొన్న"),
    "millet": ("millet", "cholam", "kambu", "ragi", "சோளம்", "கம்பு", "ராகி", "ಬೆಳೆ"),
    "turmeric": ("turmeric", "manjal", "haldi", "மஞ்சள்", "हल्दी"),
    "coconut": ("coconut", "thengai", "nariyal", "தென்னை", "நாரிகேள", "नारियल"),
    "mango": ("mango", "maampazham", "aam", "மாம்பழ", "आम"),
    "tomato": ("tomato", "thakkali", "தக்காளி", "టమాట"),
    "blackgram": ("blackgram", "black gram", "urad", "ulundu", "உளுந்து"),
    "greengram": ("greengram", "green gram", "moong", "pasipayaru", "பச்சைப்பயறு"),
    "chilli": ("chilli", "chili", "milagai", "mirchi", "மிளகாய்", "मिर्च"),
}

_DAMAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cyclone": ("cyclone", "puyal", "toofan", "tufan", "storm", "hurricane",
                "புயல்", "तूफान", "తుఫాన్", "ಚಂಡಮಾರುತ", "കൊടുങ്കാറ്റ്"),
    "flood": ("flood", "vellam", "baadh", "badh", "வெள்ளம்", "बाढ़", "వరద", "ಪ್ರವಾಹ", "വെള്ളപ്പൊക്ക"),
    "inundation": ("inundation", "waterlogging", "water logging", "submerged",
                   "thanni thengi", "जलभराव"),
    "heavy_rain": ("heavy rain", "heavyrain", "peru mazhai", "kanamazhai", "bhari barish",
                   "கனமழை", "भारी बारिश", "భారీ వర్షం"),
    "unseasonal_rain": ("unseasonal rain", "unseasonal", "besan mazhai", "bemausam"),
    "drought": ("drought", "varatchi", "sukha", "sookha", "வறட்சி", "सूखा", "కరువు", "ಬರ"),
    "hailstorm": ("hail", "hailstorm", "aalangatti", "ola vrishti", "ஆலங்கட்டி", "ओलावृष्टि"),
    "pest": ("pest", "insect", "poochi", "keet", "keeda", "பூச்சி", "कीट"),
    "disease": ("disease", "blight", "noi", "rog", "நோய்", "रोग"),
    "fire": ("fire", "thee", "aag", "தீ விபத்து", "आग"),
    "landslide": ("landslide", "nilasarivu", "bhooskhalan", "நிலச்சரிவு", "भूस्खलन"),
}

_TN_DISTRICTS_FALLBACK = [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri",
    "Dindigul", "Erode", "Kallakurichi", "Kancheepuram", "Kanyakumari", "Karur",
    "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal",
    "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem",
    "Sivaganga", "Tenkasi", "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli",
    "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai",
    "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar",
]

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "half": 0.5, "quarter": 0.25,
    "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5,
}

_UNIT_WORDS = (
    "hectares", "hectare", "acres", "acre", "cents", "cent", "bigha", "guntha",
    "kani", "ground", "ma", "ha",
)

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _normalise(text: str) -> str:
    """Lowercase + strip accents; keeps native scripts intact for substring search."""
    return unicodedata.normalize("NFKC", text or "").lower()


def _find_keyword(text: str, mapping: dict[str, tuple[str, ...]]) -> Optional[str]:
    """Substring search — robust to the STT dropping spaces between words."""
    lowered = _normalise(text)
    best: Optional[str] = None
    best_at = len(lowered) + 1
    for key, keywords in mapping.items():
        for keyword in keywords:
            needle = _normalise(keyword)
            if len(needle) <= 4:
                # short keywords ("maa", "nel") must stand alone, otherwise "maadhiri" → mango
                match = re.search(r"(?<![a-z஀-௿])" + re.escape(needle) + r"(?![a-z஀-௿])", lowered)
                at = match.start() if match else -1
            else:
                at = lowered.find(needle)
            if at >= 0 and at < best_at:
                best, best_at = key, at
    return best


def _find_all_keywords(text: str, mapping: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = _normalise(text)
    found: list[str] = []
    for key, keywords in mapping.items():
        for kw in keywords:
            needle = _normalise(kw)
            if len(needle) <= 4:
                hit = re.search(r"(?<![a-z஀-௿])" + re.escape(needle) + r"(?![a-z஀-௿])", lowered) is not None
            else:
                hit = needle in lowered
            if hit:
                found.append(key)
                break
    return found


def known_districts() -> list[str]:
    districts = providers.list_districts()
    names = [str(d.get("name")) for d in districts if isinstance(d, dict) and d.get("name")]
    return names or list(_TN_DISTRICTS_FALLBACK)


def find_district(text: str) -> Optional[str]:
    lowered = _normalise(text)
    best: Optional[str] = None
    best_at = len(lowered) + 1
    for name in known_districts():
        at = lowered.find(_normalise(name))
        if at >= 0 and at < best_at:
            best, best_at = name, at
    return best


_EXTENT_RE = re.compile(
    r"(\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\s*(?:and\s*a\s*half\s*)?"
    r"(" + "|".join(_UNIT_WORDS) + r")",
    re.IGNORECASE,
)


def find_extents(text: str) -> list[tuple[float, str]]:
    """All (value, unit) pairs; tolerates ``2acres`` with no space."""
    out: list[tuple[float, str]] = []
    for match in _EXTENT_RE.finditer(_normalise(text)):
        raw_value, unit = match.group(1), match.group(2)
        try:
            value = float(raw_value)
        except ValueError:
            value = float(_NUMBER_WORDS.get(raw_value, 0) or 0)
        if value <= 0:
            continue
        out.append((value, unit.rstrip("s") if unit not in ("cents", "ha") else unit.rstrip("s")))
    return out


def _clean_name(raw: str) -> Optional[str]:
    """Strip words the STT glued onto a name ("Priyafrom" -> "Priya")."""
    name = raw.strip().strip(".,;:")
    if not name:
        return None
    name = re.sub(
        r"(from|at|in|and|near|of|calling|speaking|here|sir|madam)$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = name.strip()
    if len(name) < 2 or name.lower() in {"the", "a", "an", "not", "sorry"}:
        return None
    return name[:1].upper() + name[1:]


_NAME_RE = re.compile(
    r"(?:my\s*name\s*is|myname\s*is|mynameis|this\s*is|thisis|i\s*am|iam|im\b"
    r"|en\s*peru|enperu|naan|mera\s*naam|meranaam|naa\s*peru|njan)"
    r"\s*([A-Za-z][A-Za-z]{1,24})",
    re.IGNORECASE,
)


def find_name(text: str) -> Optional[str]:
    for match in _NAME_RE.finditer(text or ""):
        cleaned = _clean_name(match.group(1))
        if cleaned:
            return cleaned
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def resolve_date_phrase(text: str, call_date: date) -> tuple[Optional[str], float]:
    """Best-effort absolute date for the damage event, with a confidence."""
    lowered = _normalise(text)

    # 12/09/2026 or 12-09
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year_raw = match.group(3)
        year = call_date.year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        found = _safe_date(year, month, day)
        if found and found <= call_date:
            return found.isoformat(), 0.9
        if found and not year_raw:
            earlier = _safe_date(year - 1, month, day)
            if earlier:
                return earlier.isoformat(), 0.8

    # "12 September" / "September 12" / "12September"
    month_alt = "|".join(sorted(_MONTHS, key=len, reverse=True))
    for pattern, day_first in (
        (rf"(\d{{1,2}})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?({month_alt})", True),
        (rf"({month_alt})\s*(\d{{1,2}})", False),
    ):
        match = re.search(pattern, lowered)
        if match:
            if day_first:
                day, month_name = int(match.group(1)), match.group(2)
            else:
                month_name, day = match.group(1), int(match.group(2))
            month = _MONTHS[month_name]
            found = _safe_date(call_date.year, month, day)
            if found and found > call_date:
                found = _safe_date(call_date.year - 1, month, day)
            if found:
                return found.isoformat(), 0.9

    # "3 days ago" / "two weeks back"
    number_alt = "|".join(_NUMBER_WORDS)
    match = re.search(
        rf"(\d+|{number_alt})\s*(day|days|week|weeks|month|months)\s*(?:ago|back|before|munnadi|pehle)",
        lowered,
    )
    if match:
        raw = match.group(1)
        try:
            amount = float(raw)
        except ValueError:
            amount = float(_NUMBER_WORDS.get(raw, 1) or 1)
        unit = match.group(2)
        days = amount * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
        return (call_date - timedelta(days=int(days))).isoformat(), 0.6

    if any(marker in lowered for marker in ("day before yesterday", "munthanaal", "parso")):
        return (call_date - timedelta(days=2)).isoformat(), 0.7
    if any(marker in lowered for marker in ("yesterday", "nethu", "netru", "நேற்று", "நேத்து",
                                            "kal ", "innale", "ninne", "కాల")):
        return (call_date - timedelta(days=1)).isoformat(), 0.7

    match = re.search(rf"last\s*({'|'.join(_WEEKDAYS)})", lowered)
    if match:
        target = _WEEKDAYS[match.group(1)]
        delta = (call_date.weekday() - target) % 7 or 7
        return (call_date - timedelta(days=delta)).isoformat(), 0.5

    if "last week" in lowered or "poana vaaram" in lowered or "pichle hafte" in lowered:
        return (call_date - timedelta(days=7)).isoformat(), 0.4
    if "last month" in lowered:
        return (call_date - timedelta(days=30)).isoformat(), 0.3

    return None, 0.0


def _find_all_dates(text: str, call_date: date) -> list[str]:
    """Every distinct explicit date mentioned (for contradiction detection)."""
    lowered = _normalise(text)
    found: list[str] = []
    month_alt = "|".join(sorted(_MONTHS, key=len, reverse=True))
    for match in re.finditer(rf"(\d{{1,2}})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?({month_alt})", lowered):
        day, month = int(match.group(1)), _MONTHS[match.group(2)]
        parsed = _safe_date(call_date.year, month, day)
        if parsed and parsed > call_date:
            parsed = _safe_date(call_date.year - 1, month, day)
        if parsed:
            found.append(parsed.isoformat())
    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered):
        year = int(match.group(3) or call_date.year)
        if year < 100:
            year += 2000
        parsed = _safe_date(year, int(match.group(2)), int(match.group(1)))
        if parsed:
            found.append(parsed.isoformat())
    return list(dict.fromkeys(found))


def heuristic_extract(
    turns: list[TranscriptTurn], call_date: date, language_hint: str | None = None
) -> CallExtraction:
    """Regex/keyword extractor — the deterministic path used when Gemini is off."""
    caller_text = turns_text(turns, "caller")
    all_text = turns_text(turns)
    language, languages, code_switching = detect_languages(turns)
    if language_hint:
        language = language_hint
        if language_hint not in languages:
            languages = [language_hint, *languages]

    crop = _find_keyword(caller_text or all_text, _CROP_KEYWORDS)
    damage = _find_keyword(caller_text or all_text, _DAMAGE_KEYWORDS)
    extents = find_extents(caller_text)
    event_date, confidence = resolve_date_phrase(caller_text, call_date)
    district = find_district(all_text)

    contradictions: list[str] = []
    distinct_dates = _find_all_dates(caller_text, call_date)
    if len(distinct_dates) > 1:
        contradictions.append(
            f"The caller gave more than one date for the damage: {', '.join(distinct_dates)}."
        )
    distinct_extents = {(value, unit) for value, unit in extents}
    if len(distinct_extents) > 1:
        rendered = ", ".join(f"{value:g} {unit}" for value, unit in sorted(distinct_extents))
        contradictions.append(f"The caller gave more than one land extent: {rendered}.")
    distinct_crops = _find_all_keywords(caller_text, _CROP_KEYWORDS)
    if len(distinct_crops) > 1:
        contradictions.append(
            f"The caller mentioned more than one crop: {', '.join(sorted(distinct_crops))}."
        )

    lowered_caller = _normalise(caller_text)
    distress = any(
        marker in lowered_caller
        for marker in ("suicide", "kill myself", "starving", "nothing to eat", "dying",
                       "please help", "crying", "desperate", "தற்கொலை", "आत्महत्या")
    )
    asked_for_human = any(
        marker in lowered_caller
        for marker in ("talk to a person", "speak to a person", "real person", "human",
                       "officer", "manager", "supervisor", "transfer me", "someone else",
                       "aalu", "manushan", "aadmi")
    )
    outcome_questions = [
        sentence.strip()
        for sentence in re.split(r"[.?!\n]+", caller_text)
        if sentence.strip()
        and re.search(
            r"(how much|how many rupees|when will|will i get|money|amount|approved|"
            r"eligible|compensation|kitna|eppo|எவ்வளவு|कितना|ఎంత)",
            sentence,
            re.IGNORECASE,
        )
    ]

    return CallExtraction(
        farmer_name=find_name(caller_text),
        language=language,
        languages=languages,
        code_switching=code_switching,
        crop=crop,
        land_extent_value=extents[0][0] if extents else None,
        land_extent_unit=extents[0][1] if extents else None,
        damage_type=damage,
        event_date=event_date,
        event_date_confidence=confidence,
        district=district,
        state="Tamil Nadu",
        narrative=(caller_text[:600] if caller_text else ""),
        summary=(caller_text.strip().split("\n")[0][:200] if caller_text else ""),
        distress=distress,
        asked_for_human=asked_for_human,
        outcome_questions_asked=outcome_questions[:6],
        agent_quoted_facts=_heuristic_agent_facts(turns),
        agent_listed_evidence=_heuristic_agent_evidence(turns),
        contradictions=contradictions,
    )


_EVIDENCE_HINTS = (
    "photo", "photograph", "chitta", "patta", "adangal", "passbook", "aadhaar",
    "aadhar", "receipt", "bill", "certificate", "land record", "document",
)


def _heuristic_agent_evidence(turns: list[TranscriptTurn]) -> list[str]:
    found: list[str] = []
    for turn in turns:
        if turn.role != "agent":
            continue
        lowered = _normalise(turn.text)
        for hint in _EVIDENCE_HINTS:
            if hint in lowered and hint not in found:
                found.append(hint)
    return found


_CITATION_IN_SPEECH = re.compile(r"\[([SWCDG][-\w.]*)\]")


def _heuristic_agent_facts(turns: list[TranscriptTurn]) -> list[str]:
    """Agent sentences that assert a scheme/weather/crop fact."""
    facts: list[str] = []
    for turn in turns:
        if turn.role != "agent":
            continue
        for sentence in re.split(r"[.?!\n]+", turn.text):
            sentence = sentence.strip()
            if not sentence or sentence.endswith("?"):
                continue
            if _CITATION_IN_SPEECH.search(sentence) or re.search(
                r"(scheme|pmfby|insurance rule|guideline|policy|premium|record shows|"
                r"weather record|rainfall|sowing window|crop calendar|eligib|coverage|"
                r"notified|helpline|14447)",
                sentence,
                re.IGNORECASE,
            ):
                facts.append(sentence[:240])
    return facts[:20]


async def extract(
    turns: list[TranscriptTurn], call_date: date, language_hint: str | None = None
) -> CallExtraction:
    """Gemini extraction with the deterministic extractor as backstop/filler."""
    from services import gemini

    baseline = heuristic_extract(turns, call_date, language_hint)
    if not gemini.is_available():
        return baseline

    template = gemini.load_prompt("extraction.md")
    if not template:
        return baseline
    prompt = (
        template.replace("{{CALL_DATE}}", call_date.isoformat())
        .replace("{{DEFAULT_STATE}}", "Tamil Nadu")
        .replace("{{TRANSCRIPT}}", transcript_to_text(turns))
    )

    result = await gemini.generate_json(prompt, CallExtraction)
    if result is None:
        logger.info("gemini extraction unavailable — using heuristic extraction")
        return baseline

    # Fill anything the model left empty from the deterministic pass.
    merged = result.model_copy()
    for field in (
        "farmer_name", "crop", "land_extent_value", "land_extent_unit",
        "damage_type", "event_date", "district", "taluk", "village",
    ):
        if getattr(merged, field, None) in (None, "") and getattr(baseline, field, None):
            setattr(merged, field, getattr(baseline, field))
    if not merged.languages:
        merged.languages = baseline.languages
    if not merged.narrative:
        merged.narrative = baseline.narrative
    if merged.event_date and not merged.event_date_confidence:
        merged.event_date_confidence = baseline.event_date_confidence or 0.5
    if merged.damage_type not in DAMAGE_TYPES:
        merged.damage_type = baseline.damage_type
    # never lose a deterministic contradiction the model missed
    for item in baseline.contradictions:
        if item not in merged.contradictions:
            merged.contradictions.append(item)
    return merged


# --------------------------------------------------------------------------
# 4. agent fact cross-check
# --------------------------------------------------------------------------
def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", _normalise(text)) if len(token) > 3}


def _similarity(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz

        return float(fuzz.token_set_ratio(a, b)) / 100.0
    except Exception:
        tokens_a, tokens_b = _token_set(a), _token_set(b)
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


_SCHEME_CLAIM_RE = re.compile(
    r"(scheme|pmfby|fasal bima|insurance|premium|percent|%|eligib|coverage|"
    r"sum insured|indemnity|notified|guideline|rule|helpline)",
    re.IGNORECASE,
)


def cross_check_agent_facts(
    extraction: CallExtraction, turns: list[TranscriptTurn]
) -> tuple[list[AgentSaidFact], list[GuardrailIncident], list[str]]:
    """Map what the agent asserted onto real citation ids.

    Returns ``(agent_said_facts, incidents, unknown_ids)``.  A scheme-shaped
    assertion that matches no known fact becomes a ``fabricated_scheme`` incident.
    """
    facts = providers.load_facts()
    known_ids = providers.known_citation_ids()
    said: list[AgentSaidFact] = []
    incidents: list[GuardrailIncident] = []
    unknown_ids: list[str] = []

    def turn_index_for(quote: str) -> int:
        needle = _normalise(quote)[:60]
        for turn in turns:
            if turn.role == "agent" and needle and needle in _normalise(turn.text):
                return turn.i
        return -1

    for quoted in extraction.agent_quoted_facts:
        quoted = (quoted or "").strip()
        if not quoted:
            continue

        spoken_ids = _CITATION_IN_SPEECH.findall(quoted)
        if spoken_ids:
            for cid in spoken_ids:
                verified = cid in known_ids or providers.citation_by_id(cid) is not None
                said.append(AgentSaidFact(fact_id=cid, verified=verified))
                if not verified:
                    unknown_ids.append(cid)
                    incidents.append(
                        guardrail.fabricated_scheme_incident(turn_index_for(quoted), quoted, cid)
                    )
            continue

        best_id: Optional[str] = None
        best_score = 0.0
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            text = str(fact.get("text") or "")
            if not text:
                continue
            score = _similarity(quoted, text)
            if score > best_score:
                best_id, best_score = str(fact.get("id") or ""), score

        if best_id and best_score >= 0.62:
            said.append(AgentSaidFact(fact_id=best_id, verified=True))
            continue

        if _SCHEME_CLAIM_RE.search(quoted):
            # Free-text facts that do not textually match a fact on file are recorded as
            # unverified for the reviewer.  They are NOT treated as fabrications here:
            # romanised Tamil / Hindi paraphrases rarely match the English fact text, and
            # the Gemini audit judge is the layer that flags genuine invented rules.
            label = f"unmatched:{quoted[:60]}"
            said.append(AgentSaidFact(fact_id=label, verified=False))

    return said, incidents, unknown_ids


# --------------------------------------------------------------------------
# 5. risk scoring
# --------------------------------------------------------------------------
def score_risk(
    *,
    weather_verdict: str,
    contradictions: list[str],
    hectares: Optional[float],
    crop_in_window: Optional[bool],
    event_date: Optional[str],
    call_date: date,
    damage_type: Optional[str],
    distress: bool,
    asked_for_human: bool,
    unknown_citations: list[str],
) -> Risk:
    signals: list[RiskSignal] = []

    if weather_verdict == "not_supported":
        signals.append(RiskSignal(
            code="weather_not_supported",
            description="The weather record for that place and date does not support the damage described.",
            weight=40,
        ))
    elif weather_verdict == "unverifiable":
        signals.append(RiskSignal(
            code="weather_unverifiable",
            description="The weather record could not be checked, so the account is unverified.",
            weight=25,
        ))
    elif weather_verdict == "partially_supported":
        signals.append(RiskSignal(
            code="weather_partially_supported",
            description="The weather record only partly matches the damage described.",
            weight=10,
        ))

    for item in contradictions:
        signals.append(RiskSignal(code="contradiction", description=item, weight=15))

    if hectares is not None and hectares > LARGE_EXTENT_HECTARES:
        signals.append(RiskSignal(
            code="large_extent",
            description=f"Declared extent is {hectares:g} hectares, above the {LARGE_EXTENT_HECTARES:g} ha review threshold.",
            weight=15,
        ))

    if crop_in_window is False:
        signals.append(RiskSignal(
            code="crop_out_of_window",
            description="The event date falls outside the sowing-to-harvest window for this crop and district.",
            weight=15,
        ))

    if event_date and damage_type in LOCALIZED_CALAMITIES:
        try:
            delta = (call_date - date.fromisoformat(event_date)).days
        except ValueError:
            delta = 0
        if delta > 3:
            signals.append(RiskSignal(
                code="late_intimation",
                description=f"Localised calamity reported {delta} days after the event (72-hour intimation window).",
                weight=5,
            ))

    if distress:
        signals.append(RiskSignal(
            code="distress",
            description="The caller showed distress; a person should speak with them.",
            weight=0,
        ))
    if asked_for_human:
        signals.append(RiskSignal(
            code="asked_for_human",
            description="The caller asked to speak with a person.",
            weight=0,
        ))
    for cid in unknown_citations:
        signals.append(RiskSignal(
            code="unknown_citation",
            description=f"The agent quoted a fact with no source on file ({cid}).",
            weight=20,
        ))

    score = sum(signal.weight for signal in signals)
    level = "high" if score >= ESCALATION_THRESHOLD else "medium" if score >= 20 else "low"
    return Risk(score=score, level=level, signals=signals)  # type: ignore[arg-type]


def build_farmer_explanation(reasons: list[str]) -> str:
    """Plain, non-accusatory sentence(s) the farmer can be told."""
    if not reasons:
        return (
            "A person from our team will go through your claim with you and confirm "
            "the details. Nothing is wrong with what you told us."
        )
    lead = "A person from our team will check your claim with you"
    body = " " + " ".join(reasons)
    tail = (
        " This is a normal check and it does not mean your claim is refused. "
        "Please keep your photos and land papers ready."
    )
    return (lead + " because" + body + tail).replace("  ", " ").strip()


_REASON_TEXT: dict[str, str] = {
    "weather_not_supported": (
        "the rainfall and wind readings on file for that day and place do not match "
        "the damage you described, so the date or the place may need correcting;"
    ),
    "weather_unverifiable": (
        "we could not reach the weather record just now, so a person will verify it "
        "rather than us guessing;"
    ),
    "weather_partially_supported": (
        "the weather record for that day only partly matches what you described;"
    ),
    "contradiction": "some details were given differently at different points in the call;",
    "large_extent": "the land extent you gave is large enough that it is checked by a person;",
    "crop_out_of_window": (
        "the date falls outside the usual sowing season for this crop in your district;"
    ),
    "late_intimation": "the damage was reported more than 72 hours after it happened;",
    "distress": "you sounded worried and we would rather a person spoke with you;",
    "asked_for_human": "you asked to speak with a person;",
    "unknown_citation": "one thing said on the call needs to be checked against our records;",
}


def explanation_reasons(risk: Risk) -> list[str]:
    seen: set[str] = set()
    reasons: list[str] = []
    for signal in risk.signals:
        text = _REASON_TEXT.get(signal.code)
        if text and text not in seen:
            seen.add(text)
            reasons.append(text)
    return reasons


# --------------------------------------------------------------------------
# 6. persistence helpers
# --------------------------------------------------------------------------
def _touch(row: ClaimRow) -> None:
    row.updated_at = now_iso()


def _update_claim(claim_id: int, **fields: Any) -> Claim:
    with session_scope() as session:
        row = session.get(ClaimRow, claim_id)
        if row is None:
            raise ValueError(f"claim {claim_id} disappeared")
        for key, value in fields.items():
            setattr(row, key, value)
        _touch(row)
        session.flush()
        return claim_to_schema(session, row)


async def _emit_claim(event_type: str, claim: Claim, stage: str) -> None:
    payload = claim_summary(claim)
    payload["stage"] = stage
    # always ship the full claim so live views never keep a stale partial snapshot
    payload["claim"] = claim.model_dump(mode="json")
    await emit(event_type, payload)


def _persist_incidents(
    call_id: int, claim_id: Optional[int], incidents: list[GuardrailIncident]
) -> None:
    if not incidents:
        return
    with session_scope() as session:
        for incident in incidents:
            session.add(
                GuardrailIncidentRow(
                    call_id=call_id,
                    claim_id=claim_id,
                    turn_index=incident.turn_index,
                    category=incident.category,
                    text=incident.text,
                    severity=incident.severity,
                    detector=incident.detector,
                    created_at=now_iso(),
                )
            )


def _cache_claim_citations(claim: Claim) -> None:
    with session_scope() as session:
        for citation in (
            list(claim.weather_evidence.citations)
            + list(claim.disaster_evidence.citations)
            + (list(claim.crop_evidence.citations) if claim.crop_evidence else [])
            + [match.citation for match in claim.scheme_matches]
        ):
            cache_citation(session, citation.model_dump(mode="json"))


# --------------------------------------------------------------------------
# 7. the pipeline
# --------------------------------------------------------------------------
async def process_call(call_id: int) -> Optional[Claim]:
    """Run the full pipeline for a stored call. Idempotent per call."""
    with session_scope() as session:
        row = session.get(CallRow, call_id)
        if row is None:
            logger.warning("process_call: no call %s", call_id)
            return None
        if row.processing == "processing":
            logger.info("call %s already being processed", call_id)
            return None
        row.processing = "processing"
        row.processing_error = None
        session.flush()
        raw_transcript = row.transcript_raw or ""
        stored_turns = row.transcript or []
        started_at = row.started_at
        from_number = row.from_number
        snapserve_id = row.snapserve_call_id

    try:
        claim = await _run_pipeline(
            call_id=call_id,
            raw_transcript=raw_transcript,
            stored_turns=stored_turns,
            started_at=started_at,
            from_number=from_number,
        )
    except Exception as exc:
        logger.exception("ingest failed for call %s (%s)", call_id, snapserve_id)
        with session_scope() as session:
            row = session.get(CallRow, call_id)
            if row is not None:
                row.processing = "error"
                row.processing_error = f"{exc.__class__.__name__}: {exc}"
        await emit("call.completed", {"id": call_id, "processing": "error"})
        return None
    return claim


async def _run_pipeline(
    *,
    call_id: int,
    raw_transcript: str,
    stored_turns: list,
    started_at: str,
    from_number: Optional[str],
) -> Claim:
    # -- 1. transcript -------------------------------------------------
    turns = parse_transcript(raw_transcript)
    if not turns and stored_turns:
        turns = [TranscriptTurn.model_validate(t) for t in stored_turns]

    try:
        call_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        call_dt = datetime.now(timezone.utc)
    call_date = call_dt.astimezone(IST).date()

    language, languages, code_switching = detect_languages(turns)

    # -- 2. extraction --------------------------------------------------
    extraction = await extract(turns, call_date, language)
    language = extraction.language or language
    languages = extraction.languages or languages
    code_switching = extraction.code_switching or code_switching

    for turn in turns:
        turn.language = turn.language or (language if turn.role == "caller" else "en")

    with session_scope() as session:
        row = session.get(CallRow, call_id)
        if row is not None:
            row.transcript = [t.model_dump(mode="json") for t in turns]
            row.language_detected = language
            row.languages = languages
            row.code_switching = code_switching
            row.summary = extraction.summary or row.summary

    crop = providers.normalize_crop(extraction.crop)
    land_extent = providers.normalize_land_extent(
        extraction.land_extent_value, extraction.land_extent_unit
    )
    damage_type = extraction.damage_type if extraction.damage_type in DAMAGE_TYPES else (
        extraction.damage_type or None
    )

    # -- create the claim early with partial data -----------------------
    with session_scope() as session:
        reference = next_reference(session)
        claim_row = ClaimRow(
            reference=reference,
            call_id=call_id,
            status="logged",
            farmer={
                "name": extraction.farmer_name,
                "phone": extraction.farmer_phone or from_number,
                "language": language,
            },
            crop=crop,
            land_extent=land_extent.model_dump(mode="json") if land_extent else None,
            damage_type=damage_type,
            event_date=extraction.event_date,
            event_date_confidence=extraction.event_date_confidence,
            location={},
            narrative=extraction.narrative,
            weather_evidence={},
            disaster_evidence={},
            scheme_matches=[],
            unknowns=[],
            evidence_required=[],
            risk={},
            agent_said_facts=[],
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        session.add(claim_row)
        session.flush()
        claim_id = claim_row.id
        call_row = session.get(CallRow, call_id)
        if call_row is not None:
            call_row.claim_id = claim_id
        claim = claim_to_schema(session, claim_row)

    await _emit_claim("claim.created", claim, "extracted")

    # -- 3. evidence blocks, emitted as each lands ----------------------
    data_down = settings.data_down_mode

    location = providers.resolve_location(
        extraction.village, extraction.taluk, extraction.district, extraction.state or "Tamil Nadu"
    )
    claim = _update_claim(claim_id, location=location.model_dump(mode="json"))
    await _emit_claim("claim.updated", claim, "location")

    weather = providers.check_weather(
        location.lat, location.lon, extraction.event_date, damage_type, data_down=data_down
    )
    claim = _update_claim(claim_id, weather_evidence=weather.model_dump(mode="json"))
    await _emit_claim("claim.updated", claim, "weather")

    disasters = providers.check_disasters(
        location.lat, location.lon, extraction.event_date, data_down=data_down
    )
    claim = _update_claim(claim_id, disaster_evidence=disasters.model_dump(mode="json"))
    await _emit_claim("claim.updated", claim, "disasters")

    crop_evidence = providers.check_crop_window(crop, location.district, extraction.event_date)
    claim = _update_claim(
        claim_id,
        crop_evidence=crop_evidence.model_dump(mode="json") if crop_evidence else None,
    )
    await _emit_claim("claim.updated", claim, "crop")

    scheme_matches, unknowns = providers.lookup_scheme(
        crop, location.district, extraction.event_date, damage_type
    )
    try:  # simulated TN Kharif 2026 sum-insured ceiling (never a payout)
        from services import sum_insured as _sum_insured

        _ceiling = _sum_insured.ceiling_match(
            crop, location.district, getattr(land_extent, "hectares", None)
        )
        if _ceiling is not None:
            scheme_matches = list(scheme_matches) + [_ceiling]
    except Exception as exc:  # pragma: no cover
        logger.warning("sum-insured ceiling skipped: %s", exc)
    evidence_required = providers.evidence_checklist(damage_type, crop)
    claim = _update_claim(
        claim_id,
        scheme_matches=[m.model_dump(mode="json") for m in scheme_matches],
        unknowns=unknowns,
        evidence_required=[item.model_dump(mode="json") for item in evidence_required],
    )
    await _emit_claim("claim.updated", claim, "schemes")

    _cache_claim_citations(claim)

    # -- 4/5. cross-check + guardrails ---------------------------------
    said_facts, fabrication_incidents, unknown_ids = cross_check_agent_facts(extraction, turns)
    audit_incidents = await guardrail.audit(turns)

    if (extraction.distress or extraction.asked_for_human) and turns:
        last_agent = max((t.i for t in turns if t.role == "agent"), default=-1)
        if not any(
            marker in _normalise(turns_text(turns, "agent"))
            for marker in ("a person will", "someone will call", "transfer", "reviewer will",
                           "officer will", "human")
        ):
            audit_incidents.append(
                guardrail.missed_escalation_incident(
                    last_agent,
                    "The caller asked for a person or showed distress and no handover was offered.",
                )
            )

    incidents = guardrail.merge_incidents(audit_incidents, fabrication_incidents)

    # -- risk ------------------------------------------------------------
    risk = score_risk(
        weather_verdict=weather.verdict,
        contradictions=extraction.contradictions,
        hectares=land_extent.hectares if land_extent else None,
        crop_in_window=crop_evidence.in_window if crop_evidence else None,
        event_date=extraction.event_date,
        call_date=call_date,
        damage_type=damage_type,
        distress=extraction.distress,
        asked_for_human=extraction.asked_for_human,
        unknown_citations=unknown_ids,
    )

    # -- 6. decision -----------------------------------------------------
    escalate = (
        risk.score >= ESCALATION_THRESHOLD
        or weather.verdict == "unverifiable"
        or extraction.distress
        or extraction.asked_for_human
    )
    reasons = explanation_reasons(risk)
    farmer_explanation = build_farmer_explanation(reasons) if escalate else None
    escalation_reason = (
        "; ".join(signal.description for signal in risk.signals) if escalate else None
    )

    claim = _update_claim(
        claim_id,
        status="escalated" if escalate else "logged",
        risk=risk.model_dump(mode="json"),
        agent_said_facts=[fact.model_dump(mode="json") for fact in said_facts],
        escalation_reason=escalation_reason,
        farmer_explanation=farmer_explanation,
    )

    _persist_incidents(call_id, claim_id, incidents)
    with session_scope() as session:
        call_row = session.get(CallRow, call_id)
        if call_row is not None:
            call_row.guardrail_incidents = [i.model_dump(mode="json") for i in incidents]
            call_row.processing = "done"

    for incident in incidents:
        await emit(
            "guardrail.incident",
            {
                "call_id": call_id,
                "claim_id": claim_id,
                **incident.model_dump(mode="json"),
            },
        )

    ticket_payload: Optional[dict] = None
    if escalate:
        severity = "high" if risk.score >= 60 or extraction.distress else (
            "medium" if risk.score >= 20 else "low"
        )
        with session_scope() as session:
            ticket_row = TicketRow(
                claim_id=claim_id,
                call_id=call_id,
                reference=claim.reference,
                severity=severity,
                reasons=[signal.description for signal in risk.signals] or [
                    "Escalated for a person to confirm the details."
                ],
                farmer_explanation=farmer_explanation or "",
                status="open",
                created_at=now_iso(),
                updated_at=now_iso(),
            )
            session.add(ticket_row)
            session.flush()
            call_row = session.get(CallRow, call_id)
            if call_row is not None:
                call_row.ticket_id = ticket_row.id
            ticket_payload = ticket_to_schema(ticket_row).model_dump(mode="json")

    with read_session() as session:
        row = session.get(ClaimRow, claim_id)
        claim = claim_to_schema(session, row) if row is not None else claim

    await _emit_claim("claim.updated", claim, "decided")
    if ticket_payload is not None:
        await emit("ticket.created", ticket_payload)

    logger.info(
        "claim %s: status=%s risk=%d verdict=%s incidents=%d",
        claim.reference, claim.status, risk.score, weather.verdict, len(incidents),
    )
    return claim


# --------------------------------------------------------------------------
# 8. simulation entry point (POST /api/admin/simulate)
# --------------------------------------------------------------------------
async def simulate(
    transcript: str, from_number: str | None = None, language: str | None = None
) -> CallRecord:
    """Run the full pipeline over a pasted transcript, as if it were a real call."""
    turns = parse_transcript(transcript)
    detected, languages, code_switching = detect_languages(turns)
    started = now_iso()
    sim_id = f"sim-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    with session_scope() as session:
        row = CallRow(
            snapserve_call_id=sim_id,
            agent_id=settings.snapserve_agent_id,
            direction="simulated",
            from_number=from_number,
            to_number=None,
            status="completed",
            started_at=started,
            ended_at=started,
            duration_seconds=None,
            language_detected=language or detected,
            languages=languages,
            code_switching=code_switching,
            transcript=[t.model_dump(mode="json") for t in turns],
            transcript_raw=transcript,
            processing="pending",
            raw={"simulated": True},
            created_at=started,
        )
        session.add(row)
        session.flush()
        call_id = row.id
        record = call_to_schema(row)

    await emit("call.completed", record.model_dump(mode="json"))
    await process_call(call_id)

    with read_session() as session:
        row = session.get(CallRow, call_id)
        return call_to_schema(row) if row is not None else record
