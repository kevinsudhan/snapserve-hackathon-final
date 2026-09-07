"""Scheme knowledge for FasalDesk.

Everything the voice agent may say about a government crop-insurance scheme
comes from `backend/data/schemes.json`, and every fact there carries a real
source URL, a page/section reference and a verbatim quote.

Nothing in this module invents a rule. When a question needs a number that only
a state notification can give (sum insured, indemnity level, this district's
cut-off date), `lookup_scheme` returns it as an *unknown* — a full sentence the
agent can say out loud — instead of guessing.

Public API (see docs/CONTRACTS.md):
    load_facts()
    lookup_scheme(crop, district, event_date, damage_type) -> (SchemeMatch[], unknowns[])
    evidence_checklist(damage_type, crop) -> EvidenceItem[]
    render_scheme_knowledge() -> str
    safe_scripts() -> dict
    citation_by_id(cid) -> Citation | None
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .schemes_models import Citation, EvidenceItem, SchemeMatch

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHEMES_PATH = DATA_DIR / "schemes.json"
EVIDENCE_PATH = DATA_DIR / "evidence_checklists.json"
SAFE_SCRIPTS_PATH = DATA_DIR / "safe_scripts.json"

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Damage types used across the backend (mirrors weather.DAMAGE_TYPES) plus the
#: scheme-specific stages that are not weather events.
DAMAGE_TYPES = [
    "cyclone", "flood", "inundation", "heavy_rain", "unseasonal_rain",
    "drought", "hailstorm", "pest", "disease", "fire", "landslide",
    "cloud_burst", "prevented_sowing", "post_harvest", "wild_animal", "other",
]

_DAMAGE_ALIASES = {
    "cyclone": "cyclone", "storm": "cyclone", "cyclonic_rain": "cyclone",
    "typhoon": "cyclone", "gale": "cyclone",
    "flood": "flood", "flooding": "flood", "floods": "flood",
    "inundation": "inundation", "waterlogging": "inundation",
    "water_logging": "inundation", "submergence": "inundation",
    "heavy_rain": "heavy_rain", "excess_rain": "heavy_rain",
    "heavy_rainfall": "heavy_rain",
    "unseasonal_rain": "unseasonal_rain", "untimely_rain": "unseasonal_rain",
    "drought": "drought", "dry_spell": "drought", "deficit_rain": "drought",
    "hailstorm": "hailstorm", "hail": "hailstorm",
    "pest": "pest", "pests": "pest", "insect": "pest",
    "disease": "disease", "blast": "disease", "blight": "disease",
    "fire": "fire", "lightning": "fire", "natural_fire": "fire",
    "landslide": "landslide", "landslip": "landslide",
    "cloud_burst": "cloud_burst", "cloudburst": "cloud_burst",
    "prevented_sowing": "prevented_sowing", "failed_sowing": "prevented_sowing",
    "post_harvest": "post_harvest", "postharvest": "post_harvest",
    "post_harvest_loss": "post_harvest",
    "wild_animal": "wild_animal", "elephant": "wild_animal", "boar": "wild_animal",
}

_CROP_ALIASES = {
    "paddy": "paddy", "rice": "paddy", "nel": "paddy", "vari": "paddy",
    "dhan": "paddy", "samba": "paddy", "kuruvai": "paddy", "thaladi": "paddy",
    "groundnut": "groundnut", "peanut": "groundnut", "kadalai": "groundnut",
    "moongphali": "groundnut",
    "blackgram": "black gram", "black gram": "black gram", "urad": "black gram",
    "ulundu": "black gram",
    "greengram": "green gram", "green gram": "green gram", "moong": "green gram",
    "pasipayaru": "green gram",
    "pigeonpea": "pigeon pea", "pigeon pea": "pigeon pea", "tur": "pigeon pea",
    "arhar": "pigeon pea", "thuvaram": "pigeon pea",
    "pearlmillet": "pearl millet", "pearl millet": "pearl millet",
    "bajra": "pearl millet", "kambu": "pearl millet",
    "sesame": "sesame", "gingelly": "sesame", "til": "sesame", "ellu": "sesame",
    "bhindi": "bhindi", "okra": "bhindi", "ladysfinger": "bhindi",
    "vendakkai": "bhindi",
    "brinjal": "brinjal", "eggplant": "brinjal", "kathirikai": "brinjal",
    "banana": "banana", "vazhai": "banana",
    "tapioca": "tapioca", "cassava": "tapioca", "maravalli": "tapioca",
    "turmeric": "turmeric", "manjal": "turmeric",
    "sugarcane": "sugarcane", "karumbu": "sugarcane",
    "cotton": "cotton", "parutti": "cotton",
    "maize": "maize", "makkacholam": "maize", "corn": "maize",
}

#: Only used to work out which state a district belongs to, so that
#: state-level facts (e.g. the Tamil Nadu notification) can be matched from a
#: district name alone. Location resolution itself belongs to gazetteer.py.
_DISTRICT_STATE = {
    d.lower(): "Tamil Nadu"
    for d in [
        "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore",
        "Dharmapuri", "Dindigul", "Erode", "Kallakurichi", "Kanchipuram",
        "Kanyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai",
        "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai",
        "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi",
        "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli",
        "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai", "Tiruvarur",
        "Vellore", "Viluppuram", "Virudhunagar",
    ]
}

#: Damage types where the loss is judged on the individual farm and the farmer
#: has to lodge an intimation.
_INDIVIDUAL_ASSESSMENT = {
    "hailstorm", "landslide", "inundation", "fire", "cloud_burst",
    "post_harvest", "cyclone", "unseasonal_rain",
}

_FIELD_HEADINGS = [
    ("purpose", "What the scheme is"),
    ("who_can_enrol", "Who can be covered"),
    ("enrolment", "How and when a farmer joins"),
    ("crops_covered", "Which crops"),
    ("risks_covered", "What is covered"),
    ("exclusions", "What is not covered"),
    ("intimation", "Reporting a loss"),
    ("premium", "What the farmer pays"),
    ("sum_insured", "How the cover amount is fixed"),
    ("assessment", "How the loss is checked"),
    ("evidence", "What evidence is used"),
    ("claim_timeline", "Timelines in the guidelines (NEVER promise these)"),
    ("claim_payment", "How a settled claim is paid"),
    ("grievance", "If the farmer is unhappy"),
    ("helpline", "Government helpline"),
    ("documents", "Papers a farmer needs"),
    ("state_notification", "State-specific facts"),
    ("portal", "Where the records live"),
]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _schemes_doc() -> dict:
    return _read_json(SCHEMES_PATH)


@lru_cache(maxsize=1)
def _evidence_doc() -> dict:
    return _read_json(EVIDENCE_PATH)


@lru_cache(maxsize=1)
def _safe_scripts_doc() -> dict:
    return _read_json(SAFE_SCRIPTS_PATH)


def load_facts() -> list[dict]:
    """Every scheme fact, exactly as stored in backend/data/schemes.json."""
    return list(_schemes_doc()["facts"])


@lru_cache(maxsize=1)
def _facts_by_id() -> dict[str, dict]:
    return {f["id"]: f for f in load_facts()}


def reload_data() -> None:
    """Drop the caches so edited JSON is picked up without a restart."""
    for fn in (_schemes_doc, _evidence_doc, _safe_scripts_doc, _facts_by_id):
        fn.cache_clear()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _slug(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def normalize_damage_type(text: Optional[str]) -> Optional[str]:
    """Map a free-text damage word onto the scheme vocabulary."""
    key = _slug(text)
    if not key:
        return None
    if key in _DAMAGE_ALIASES:
        return _DAMAGE_ALIASES[key]
    for alias, canonical in _DAMAGE_ALIASES.items():
        if alias in key:
            return canonical
    return "other"


def _normalize_crop(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    key = text.strip().lower()
    if key in _CROP_ALIASES:
        return _CROP_ALIASES[key]
    squashed = re.sub(r"[^a-z]", "", key)
    if squashed in _CROP_ALIASES:
        return _CROP_ALIASES[squashed]
    return key


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def season_for_date(event_date: Optional[str]) -> Optional[str]:
    """Broad season label for a date. June-September is kharif, October-March
    is rabi, April-May is the summer/special season. States shift these, which
    is why the cut-off date itself is always returned as an unknown."""
    parsed = _parse_date(event_date)
    if parsed is None:
        return None
    month = parsed.month
    if 6 <= month <= 9:
        return "kharif"
    if month >= 10 or month <= 3:
        return "rabi"
    return "summer"


def _state_for(district: Optional[str]) -> Optional[str]:
    if not district:
        return None
    key = district.strip().lower()
    if key in _DISTRICT_STATE:
        return _DISTRICT_STATE[key]
    for name, state in _DISTRICT_STATE.items():
        if name in key or key in name:
            return state
    # The caller may have handed us a state name rather than a district.
    if key in {s.lower() for s in _DISTRICT_STATE.values()}:
        return district.strip().title()
    return None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _listed(values: Any) -> Optional[list[str]]:
    """None means 'applies everywhere'; a list means 'only these'."""
    if values in (None, "all", "ALL"):
        return None
    if isinstance(values, str):
        return [values.lower()]
    return [str(v).lower() for v in values]


def _place_matches(applies_to: dict, district: Optional[str]) -> bool:
    states = _listed(applies_to.get("states"))
    districts = _listed(applies_to.get("districts"))
    if states is None and districts is None:
        return True
    if not district:
        return False
    key = district.strip().lower()
    if districts is not None:
        if any(d == key or d in key or key in d for d in districts):
            return True
        if states is None:
            return False
    if states is not None:
        state = _state_for(district)
        if state and state.lower() in states:
            return True
    return False


def _crop_matches(applies_to: dict, crop: Optional[str]) -> bool:
    crops = _listed(applies_to.get("crops"))
    if crops is None:
        return True
    if not crop:
        return False
    normalized = (_normalize_crop(crop) or "").lower()
    return any(c == normalized or c in normalized or normalized in c for c in crops)


def _season_matches(applies_to: dict, season: Optional[str]) -> bool:
    seasons = applies_to.get("seasons") or []
    if not seasons:
        return True
    if season is None:
        return True  # date unknown: keep the fact, and say the date is unknown
    return season.lower() in [s.lower() for s in seasons]


def _event_matches(applies_to: dict, damage_type: Optional[str]) -> bool:
    events = applies_to.get("events") or []
    if not events:
        return True  # general fact, always relevant
    if damage_type is None:
        return False
    return damage_type in [str(e).lower() for e in events]


def _fact_sort_key(fact: dict) -> tuple:
    match = re.match(r"S(\d+)", fact["id"])
    return (int(match.group(1)) if match else 9999, fact["id"])


#: Fields that are worth showing on a claim record even when they are not
#: specific to the event, because a reviewer always wants them in front of them.
_ALWAYS_USEFUL_FIELDS = {
    "purpose", "who_can_enrol", "exclusions", "helpline", "documents",
    "premium", "claim_timeline", "grievance", "state_notification",
}

#: Facts a reviewer should see on every claim, whatever the event: what the
#: scheme is, what it never covers, and where the farmer can complain.
_PINNED_FACT_IDS = ("S1", "S31", "S71")
_EVENT_RELEVANT_FIELDS = {"intimation", "risks_covered", "evidence", "assessment"}


def _relevance(fact: dict) -> int:
    """How specific this fact is to the claim in hand. Higher comes first."""
    applies = fact.get("applies_to") or {}
    score = 0
    if applies.get("events"):
        score += 8
    if _listed(applies.get("districts")) is not None:
        score += 7
    elif _listed(applies.get("states")) is not None:
        score += 6
    if _listed(applies.get("crops")) is not None:
        score += 4
    if applies.get("seasons"):
        score += 2
    if fact["field"] in _EVENT_RELEVANT_FIELDS:
        score += 2
    if fact["field"] in _ALWAYS_USEFUL_FIELDS:
        score += 1
    return score


def _to_match(fact: dict) -> SchemeMatch:
    return SchemeMatch(
        fact_id=fact["id"],
        scheme=fact["scheme"],
        field=fact["field"],
        text=fact["text"],
        citation=Citation(**fact["citation"]),
    )


def lookup_scheme(
    crop: Optional[str] = None,
    district: Optional[str] = None,
    event_date: Optional[str] = None,
    damage_type: Optional[str] = None,
    *,
    limit: int = 30,
) -> tuple[list[SchemeMatch], list[str]]:
    """Return the scheme facts that apply to one claim, plus the honest gaps.

    Facts are ranked by how specific they are to this claim and capped at
    `limit`, so a claim record shows the facts a reviewer actually needs rather
    than the whole rulebook. `unknowns` are complete sentences the agent can
    speak; they always name who settles the question instead of leaving the
    farmer with nothing.
    """
    damage = normalize_damage_type(damage_type)
    season = season_for_date(event_date)
    crop_norm = _normalize_crop(crop)
    state = _state_for(district)

    applicable: list[dict] = []
    for fact in load_facts():
        applies = fact.get("applies_to") or {}
        if not _place_matches(applies, district):
            continue
        if not _crop_matches(applies, crop):
            continue
        if not _season_matches(applies, season):
            continue
        if not _event_matches(applies, damage):
            continue
        applicable.append(fact)

    applicable.sort(key=lambda f: (-_relevance(f), _fact_sort_key(f)))
    if limit and limit > 0:
        kept = applicable[:limit]
        kept_ids = {f["id"] for f in kept}
        # Always keep the pinned facts, even if more specific ones crowded them out.
        kept += [f for f in applicable
                 if f["id"] in _PINNED_FACT_IDS and f["id"] not in kept_ids]
    else:
        kept = applicable
    matches = [_to_match(f) for f in sorted(kept, key=_fact_sort_key)]

    crop_words = crop_norm or "this crop"
    place_words = district or "this district"
    season_words = season or "this season"

    unknowns: list[str] = [
        f"The exact sum insured for {crop_words} in {place_words} this season is set by the "
        f"state notification for that season, and I do not have it here; the reviewer will confirm it.",
        f"The indemnity level and the threshold yield fixed for {crop_words} in your insurance unit "
        f"are in the state notification, and I do not have them; the reviewer will check them.",
        f"Whether your own enrolment and premium are on the crop insurance portal for {season_words} "
        f"is something I cannot look up from here; the reviewer will check the record.",
        "How much would be settled in your case, and when, is decided from the field survey and the "
        "records, so I cannot tell you that; a reviewer will speak to you about it.",
    ]

    if not district:
        unknowns.append(
            "I do not have your district yet, so I cannot tell you which company is running the "
            "scheme in your area this season; the reviewer will confirm it."
        )
    elif not any(m.field == "state_notification" for m in matches):
        unknowns.append(
            f"I do not have the notification for {place_words} for this season, so I cannot tell you "
            f"which crops are notified there or which company is running it; the reviewer will confirm it."
        )

    if not event_date:
        unknowns.append(
            "I do not have the date of the damage yet, and the date decides which part of the cover "
            "applies, so a reviewer will go through it with you."
        )

    if damage in _INDIVIDUAL_ASSESSMENT:
        unknowns.append(
            f"Whether the add-on cover for this kind of loss is notified for {place_words} this season "
            f"is in the state notification, and I do not have it; the reviewer will confirm it."
        )

    if damage == "post_harvest":
        unknowns.append(
            f"The normal harvesting dates notified for {crop_words} in your area decide whether the "
            f"post-harvest cover applies, and I do not have them; the reviewer will check them."
        )

    if damage == "other" or damage is None:
        unknowns.append(
            "I am not sure yet which listed risk your loss falls under, so I will write down exactly "
            "what you described and let a reviewer place it correctly."
        )

    if state and state != "Tamil Nadu":
        unknowns.append(
            f"My notification details are for Tamil Nadu, so for {place_words} I do not have the "
            f"state-level details; the reviewer will confirm them."
        )

    return matches, unknowns


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def _evidence_item(raw: dict) -> EvidenceItem:
    return EvidenceItem(
        key=raw["key"],
        label=raw["label"],
        label_local=raw.get("label_local"),
        why=raw["why"],
        citation_id=raw.get("citation_id"),
        required=bool(raw.get("required", True)),
    )


def evidence_checklist(
    damage_type: Optional[str] = None,
    crop: Optional[str] = None,
) -> list[EvidenceItem]:
    """Photos and papers to ask this farmer for, in the order to say them."""
    doc = _evidence_doc()
    damage = normalize_damage_type(damage_type)

    ordered: list[dict] = list(doc["base"])
    for extra in doc.get("by_damage_type", {}).get(damage or "", []):
        ordered.append(extra)

    seen: set[str] = set()
    items: list[EvidenceItem] = []
    for raw in ordered:
        if raw["key"] in seen:
            continue
        seen.add(raw["key"])
        items.append(_evidence_item(raw))
    return items


def evidence_instructions(key: str) -> Optional[str]:
    """The spoken 'how to take this photo' line for one checklist item."""
    doc = _evidence_doc()
    pools = [doc["base"]] + list(doc.get("by_damage_type", {}).values())
    for pool in pools:
        for raw in pool:
            if raw["key"] == key:
                return raw.get("instructions")
    return None


def land_record_name(state: Optional[str] = None) -> str:
    """What the land record is called in a given state, for the agent to say."""
    names = _evidence_doc().get("land_record_names", {})
    if state:
        for name, label in names.items():
            if name.lower() == state.strip().lower():
                return label
    return names.get("default", "your land record")


# ---------------------------------------------------------------------------
# Rendering into the system prompt
# ---------------------------------------------------------------------------

def render_scheme_knowledge() -> str:
    """The `{{SCHEME_KNOWLEDGE}}` block: every fact with its `[S#]` id."""
    facts = sorted(load_facts(), key=_fact_sort_key)
    by_field: dict[str, list[dict]] = {}
    for fact in facts:
        by_field.setdefault(fact["field"], []).append(fact)

    known = [f for f, _ in _FIELD_HEADINGS]
    ordering = _FIELD_HEADINGS + [
        (f, f.replace("_", " ").title()) for f in by_field if f not in known
    ]

    lines: list[str] = [
        "SCHEME FACTS. Each line is one fact you may state. The id in square "
        "brackets is for the record only — never read an id out loud. Say the "
        "source in words instead, for example \"according to the government "
        "crop insurance guidelines\". If something a caller asks is not on this "
        "list, say you do not have it and that a reviewer will confirm it.",
        "",
    ]
    for field, heading in ordering:
        group = by_field.get(field)
        if not group:
            continue
        lines.append(f"## {heading}")
        for fact in group:
            flag = " [NEVER PROMISE THIS — say the guidelines set a target and the reviewer confirms]" \
                if fact.get("sensitivity") == "never_promise" else ""
            scope = _scope_note(fact.get("applies_to") or {})
            lines.append(f"[{fact['id']}] ({fact['scheme']}{scope}) {fact['text']}{flag}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _scope_note(applies_to: dict) -> str:
    bits = []
    districts = _listed(applies_to.get("districts"))
    states = _listed(applies_to.get("states"))
    seasons = applies_to.get("seasons") or []
    if districts:
        bits.append("only " + "/".join(d.title() for d in districts))
    elif states:
        bits.append("only " + "/".join(s.title() for s in states))
    if seasons:
        bits.append("/".join(seasons))
    return ", " + ", ".join(bits) if bits else ""


def render_evidence_checklists() -> str:
    """The `{{EVIDENCE_CHECKLISTS}}` block."""
    doc = _evidence_doc()
    lines = [
        "EVIDENCE CHECKLISTS. Ask for these after you have the damage type. "
        "Say them one at a time in plain words, never as a list read at speed. "
        "Give the reason in the caller's own terms, then say a reviewer will "
        "send a link on this number for the photos.",
        "",
        "## Always",
    ]
    for raw in doc["base"]:
        need = "needed" if raw.get("required", True) else "helpful if possible"
        lines.append(f"- {raw['label']} ({need}) — {raw['why']} How: {raw['instructions']}")
    lines.append("")
    lines.append("## Extra, depending on what happened")
    for damage, extras in doc.get("by_damage_type", {}).items():
        for raw in extras:
            need = "needed" if raw.get("required", True) else "helpful if possible"
            lines.append(
                f"- if the damage is {damage.replace('_', ' ')}: {raw['label']} "
                f"({need}) — {raw['why']} How: {raw['instructions']}"
            )
    lines.append("")
    lines.append("## What the land record is called")
    for state, label in doc.get("land_record_names", {}).items():
        lines.append(f"- {state}: {label}")
    return "\n".join(lines).rstrip() + "\n"


def render_safe_scripts() -> str:
    """The `{{SAFE_SCRIPTS}}` block."""
    doc = safe_scripts()
    lines = [
        "SAFE SCRIPTS. Use these every time, however the question is phrased "
        "and in whatever language it comes. Speak them in the caller's language "
        "in your own natural wording, but never add an amount, an outcome or a "
        "time to them.",
        "",
        doc.get("rendering_rule", ""),
        "",
    ]

    def block(title: str, node: dict) -> None:
        lines.append(f"## {title}")
        if node.get("when"):
            lines.append(f"Use when: {node['when']}")
        if node.get("say"):
            lines.append(f"Say: {node['say']}")
        if node.get("if_caller_insists"):
            lines.append(f"If the caller insists, once more, warmly: {node['if_caller_insists']}")
        if node.get("never"):
            lines.append("Never say: " + "; ".join(node["never"]) + ".")
        lines.append("")

    titles = {
        "payout_question": "When asked how much money",
        "approval_question": "When asked whether it will pass",
        "timeline_question": "When asked when the money or the officer comes",
        "yes_or_no_demand": "When pressed for a yes or a no",
        "will_someone_come": "When asked whether someone will visit the field",
        "data_unavailable": "When you cannot check something",
    }
    for key, title in titles.items():
        node = doc.get(key)
        if isinstance(node, dict):
            block(title, node)

    esc = doc.get("escalation", {})
    lines.append("## Explaining an escalation to the farmer")
    if esc.get("shared_opening"):
        lines.append(f"Open with: {esc['shared_opening']}")
    if esc.get("shared_closing"):
        lines.append(f"Close with: {esc['shared_closing']}")
    for key, node in esc.items():
        if not isinstance(node, dict):
            continue
        lines.append(f"- {key.replace('_', ' ')}: {node.get('say', '')}")
        if node.get("never"):
            lines.append("  Never say: " + "; ".join(node["never"]) + ".")
    lines.append("")

    probes = doc.get("contradiction_probes", {})
    if probes:
        lines.append("## Gentle probes when something does not add up")
        for key, text in probes.items():
            lines.append(f"- {key.replace('_', ' ')}: {text}")
        lines.append("")

    closing = doc.get("closing", {})
    if closing:
        lines.append("## Closing the call")
        for key, text in closing.items():
            lines.append(f"- {key.replace('_', ' ')}: {text}")
        lines.append("")

    oos = doc.get("out_of_scope", {})
    if oos:
        lines.append("## Outside what this desk handles")
        for key, text in oos.items():
            lines.append(f"- {key.replace('_', ' ')}: {text}")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Scripts and citations
# ---------------------------------------------------------------------------

def safe_scripts() -> dict:
    """Canonical English scripts for the questions that must never be answered
    with an outcome. The agent renders them in the caller's language."""
    return dict(_safe_scripts_doc())


def citation_by_id(cid: str) -> Optional[Citation]:
    """Resolve a citation id. Only `S#` ids belong to this module; weather,
    crop and gazetteer ids are owned elsewhere and resolve to None here."""
    if not cid:
        return None
    fact = _facts_by_id().get(cid.strip())
    if fact is None:
        return None
    return Citation(**fact["citation"])


def all_citations() -> list[Citation]:
    """Every scheme citation, for the CRM sources list."""
    return [Citation(**f["citation"]) for f in sorted(load_facts(), key=_fact_sort_key)]
